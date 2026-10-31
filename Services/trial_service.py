"""
Trial Management Service
Handles trial expiration checks and notifications
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging

from Models.tenant_user import Tenant, TenantStatus
from Models.security_event import SecurityEvent, EventSeverity

logger = logging.getLogger(__name__)


class TrialService:
    """Service for managing trial periods and expiration"""
    
    @staticmethod
    async def check_expired_trials() -> Dict[str, int]:
        """
        Check for expired trials and update tenant status
        Handles Day 0 (soft lockout) and Day +7 (suspension)
        
        Returns:
            Dictionary with counts of processed tenants
        """
        now = datetime.now(timezone.utc)
        
        # Find tenants with expired trials
        expired_tenants = await Tenant.find(
            Tenant.status == TenantStatus.trial,
            Tenant.trial_ends_at < now,
            Tenant.deleted_at == None
        ).to_list()
        
        suspended_count = 0
        converted_count = 0
        grace_period_count = 0
        
        for tenant in expired_tenants:
            try:
                # Check if tenant has payment method
                has_payment = await TrialService._has_payment_method(tenant.id)
                
                if has_payment:
                    # Convert to active subscription
                    tenant.status = TenantStatus.active
                    await tenant.save()
                    converted_count += 1
                    
                    logger.info(f"✅ Tenant {tenant.name} ({tenant.id}) converted to active subscription")
                    
                    # Log security event
                    await TrialService._log_security_event(
                        tenant_id=tenant.id,
                        event_type="trial_converted",
                        severity=EventSeverity.info,
                        metadata={
                            "tenant_name": tenant.name,
                            "trial_ended_at": tenant.trial_ends_at.isoformat(),
                            "converted_at": now.isoformat()
                        }
                    )
                    
                    # Send conversion confirmation email
                    await TrialService._send_trial_converted_email(tenant)
                    
                else:
                    # Check how many days it has been expired
                    trial_ends = tenant.trial_ends_at
                    if trial_ends.tzinfo is None:
                        trial_ends = trial_ends.replace(tzinfo=timezone.utc)
                    days_expired = (now - trial_ends).days
                    
                    if days_expired >= 7:
                        # Suspend account - 7 days past expiration without payment
                        tenant.status = TenantStatus.suspended
                        await tenant.save()
                        suspended_count += 1
                        
                        logger.warning(f"⚠️ Tenant {tenant.name} ({tenant.id}) suspended - 7 days past trial expiration")
                        
                        # Log security event
                        await TrialService._log_security_event(
                            tenant_id=tenant.id,
                            event_type="trial_expired_suspended",
                            severity=EventSeverity.warning,
                            metadata={
                                "tenant_name": tenant.name,
                                "trial_ended_at": tenant.trial_ends_at.isoformat(),
                                "suspended_at": now.isoformat(),
                                "reason": "no_payment_method_after_grace_period"
                            }
                        )
                        
                        # Send suspension email
                        await TrialService._send_trial_suspended_email(tenant)
                    else:
                        # In grace period (Day 0 to Day 6). Soft lockout active.
                        grace_period_count += 1
                        logger.info(f"ℹ️ Tenant {tenant.name} ({tenant.id}) in grace period. Days expired: {days_expired}")
                        
                        if days_expired == 0:
                            # Log the start of soft lockout
                            await TrialService._log_security_event(
                                tenant_id=tenant.id,
                                event_type="trial_expired_grace_period",
                                severity=EventSeverity.warning,
                                metadata={
                                    "tenant_name": tenant.name,
                                    "trial_ended_at": tenant.trial_ends_at.isoformat(),
                                    "grace_period_started_at": now.isoformat()
                                }
                            )
                            # Send trial expired email (Day 0)
                            await TrialService._send_trial_expired_email(tenant)
                    
            except Exception as e:
                logger.error(f"Error processing expired trial for tenant {tenant.id}: {str(e)}", exc_info=True)
                continue
        
        logger.info(f"Trial expiry check completed: {converted_count} converted, {suspended_count} suspended, {grace_period_count} in grace period")
        
        return {
            "total_expired": len(expired_tenants),
            "converted_to_active": converted_count,
            "suspended": suspended_count,
            "in_grace_period": grace_period_count
        }

    @staticmethod
    async def process_data_retention() -> Dict[str, int]:
        """
        Process automated deletion of suspended tenants (Day +90)
        """
        now = datetime.now(timezone.utc)
        
        # Tenants are suspended at Day +7, so Day +90 means trial_ends_at + 97 days
        cutoff_date = now - timedelta(days=97)
        
        # Find tenants to delete
        tenants_to_delete = await Tenant.find(
            Tenant.status == TenantStatus.suspended,
            Tenant.trial_ends_at < cutoff_date,
            Tenant.deleted_at == None
        ).to_list()
        
        deleted_count = 0
        
        for tenant in tenants_to_delete:
            try:
                # Soft delete the tenant
                tenant.deleted_at = now
                await tenant.save()
                deleted_count += 1
                
                logger.warning(f"🗑️ Tenant {tenant.name} ({tenant.id}) marked for deletion - 90 days suspended")
                
                # Log security event
                await TrialService._log_security_event(
                    tenant_id=tenant.id,
                    event_type="tenant_deleted",
                    severity=EventSeverity.critical,
                    metadata={
                        "tenant_name": tenant.name,
                        "deleted_at": now.isoformat(),
                        "reason": "data_retention_policy_90_days"
                    }
                )
                
            except Exception as e:
                logger.error(f"Error processing deletion for tenant {tenant.id}: {str(e)}", exc_info=True)
                continue
                
        return {
            "deleted_tenants": deleted_count
        }
    
    @staticmethod
    async def send_trial_reminders() -> Dict[str, int]:
        """
        Send reminder emails before trial expires
        
        Sends reminders at:
        - 7 days before expiry
        - 3 days before expiry
        - 1 day before expiry
        
        Returns:
            Dictionary with counts of reminders sent
        """
        now = datetime.now(timezone.utc)
        
        # Calculate time windows
        def get_window(days: int):
            target = now + timedelta(days=days)
            return (
                target.replace(hour=0, minute=0, second=0, microsecond=0),
                target.replace(hour=23, minute=59, second=59, microsecond=999999)
            )
            
        seven_days_start, seven_days_end = get_window(7)
        three_days_start, three_days_end = get_window(3)
        one_day_start, one_day_end = get_window(1)
        
        # Find tenants using Beanie queries
        tenants_to_remind = await Tenant.find(
            Tenant.status == TenantStatus.trial,
            Tenant.deleted_at == None,
            {
                "$or": [
                    {"trial_ends_at": {"$gte": seven_days_start, "$lte": seven_days_end}},
                    {"trial_ends_at": {"$gte": three_days_start, "$lte": three_days_end}},
                    {"trial_ends_at": {"$gte": one_day_start, "$lte": one_day_end}}
                ]
            }
        ).to_list()
        
        reminders_sent = 0
        
        for tenant in tenants_to_remind:
            try:
                trial_ends = tenant.trial_ends_at
                if trial_ends.tzinfo is None:
                    trial_ends = trial_ends.replace(tzinfo=timezone.utc)
                days_remaining = (trial_ends - now).days
                
                # Send appropriate reminder
                if days_remaining in [7, 3, 1]:
                    await TrialService._send_trial_reminder_email(tenant, days_remaining=days_remaining)
                    reminders_sent += 1
                    logger.info(f"📧 Sent {days_remaining}-day reminder to {tenant.name} ({tenant.id})")
                
            except Exception as e:
                logger.error(f"Error sending reminder to tenant {tenant.id}: {str(e)}", exc_info=True)
                continue
        
        logger.info(f"Trial reminders sent: {reminders_sent}")
        
        return {
            "reminders_sent": reminders_sent
        }
    
    @staticmethod
    async def get_trial_status(tenant_id: str) -> Dict[str, Any]:
        """
        Get trial status for a tenant
        
        Returns:
            Dictionary with trial information
        """
        from uuid import UUID
        
        tenant = await Tenant.find_one(Tenant.id == UUID(tenant_id))
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        now = datetime.now(timezone.utc)
        
        if tenant.status != TenantStatus.trial:
            return {
                "is_trial": False,
                "status": tenant.status.value,
                "trial_ended": True
            }
        
        trial_ends = tenant.trial_ends_at
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
            
        days_remaining = (trial_ends - now).days
        hours_remaining = (trial_ends - now).total_seconds() / 3600
        
        return {
            "is_trial": True,
            "status": "trial",
            "trial_ends_at": tenant.trial_ends_at.isoformat(),
            "days_remaining": max(0, days_remaining),
            "hours_remaining": max(0, int(hours_remaining)),
            "is_expired": trial_ends < now,
            "has_payment_method": await TrialService._has_payment_method(tenant.id)
        }
    
    @staticmethod
    async def _has_payment_method(tenant_id) -> bool:
        """
        Check if tenant has a payment method configured or active paid subscription
        """
        try:
            from Models.billing import TenantSubscription, SubscriptionStatus, Invoice, InvoiceStatus
            from uuid import UUID
            if isinstance(tenant_id, str):
                tenant_id = UUID(tenant_id)
            
            # Check active subscription
            sub = await TenantSubscription.find_one(
                TenantSubscription.tenant_id == tenant_id
            )
            if sub:
                if sub.status in [SubscriptionStatus.active, SubscriptionStatus.trialing]:
                    return True
                if len(sub.payment_methods) > 0:
                    return True
                if sub.stripe_subscription_id or sub.stripe_customer_id:
                    return True

            # Check paid invoices
            invoice = await Invoice.find_one(
                Invoice.tenant_id == tenant_id,
                Invoice.status == InvoiceStatus.paid
            )
            if invoice:
                return True
        except Exception as e:
            logger.error(f"Error checking payment method for tenant {tenant_id}: {str(e)}")
        
        return False
    
    @staticmethod
    async def _log_security_event(
        tenant_id,
        event_type: str,
        severity: EventSeverity,
        metadata: Dict[str, Any]
    ):
        """Log security event for trial actions"""
        security_event = SecurityEvent(
            tenant_id=tenant_id,
            user_id=None,
            event_type=event_type,
            severity=severity,
            actor_id=None,
            ip_address=None,
            user_agent=None,
            metadata_json=metadata
        )
        await security_event.insert()

    @staticmethod
    async def _get_tenant_admin(tenant: Tenant):
        from Models.tenant_user import User, UserType
        admin_user = await User.find_one(
            User.tenant_id == tenant.id,
            User.user_type == UserType.tenant_admin,
            User.deleted_at == None
        )
        if not admin_user:
            admin_user = await User.find_one(
                User.tenant_id == tenant.id,
                User.role == "hr_admin",
                User.deleted_at == None
            )
        return admin_user
    
    @staticmethod
    async def _send_trial_reminder_email(tenant: Tenant, days_remaining: int):
        """Send trial reminder email"""
        admin_user = await TrialService._get_tenant_admin(tenant)
        if admin_user:
            from Utility.email_service import EmailService
            EmailService.send_trial_reminder_email(
                to_email=admin_user.email,
                first_name=admin_user.first_name,
                company_name=tenant.name,
                days_remaining=days_remaining
            )
        else:
            logger.warning(f"No admin user found to send trial reminder for tenant {tenant.id}")
    
    @staticmethod
    async def _send_trial_expired_email(tenant: Tenant):
        """Send trial expired email (Day 0 Soft Lockout)"""
        admin_user = await TrialService._get_tenant_admin(tenant)
        if admin_user:
            from Utility.email_service import EmailService
            EmailService.send_trial_expired_email(
                to_email=admin_user.email,
                first_name=admin_user.first_name,
                company_name=tenant.name
            )
        else:
            logger.warning(f"No admin user found to send trial expired email for tenant {tenant.id}")

    @staticmethod
    async def _send_trial_suspended_email(tenant: Tenant):
        """Send account suspended email (Day +7)"""
        admin_user = await TrialService._get_tenant_admin(tenant)
        if admin_user:
            from Utility.email_service import EmailService
            EmailService.send_trial_suspended_email(
                to_email=admin_user.email,
                first_name=admin_user.first_name,
                company_name=tenant.name
            )
        else:
            logger.warning(f"No admin user found to send trial suspended email for tenant {tenant.id}")
    
    @staticmethod
    async def _send_trial_converted_email(tenant: Tenant):
        """Send trial converted to paid email"""
        admin_user = await TrialService._get_tenant_admin(tenant)
        if admin_user:
            from Utility.email_service import EmailService
            EmailService.send_trial_converted_email(
                to_email=admin_user.email,
                first_name=admin_user.first_name,
                company_name=tenant.name
            )
        else:
            logger.warning(f"No admin user found to send trial converted email for tenant {tenant.id}")
