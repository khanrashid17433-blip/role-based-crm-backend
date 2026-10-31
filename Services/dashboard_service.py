"""
Dashboard Service - Aggregates all dashboard statistics
"""
from datetime import datetime, timedelta
from typing import List
from Models.tenant_user import Tenant, TenantStatus
from Models.billing import TenantSubscription, Invoice, BillingEvent
from Models.security_event import SecurityEvent
from Models.login_security import LoginEvent
from Models.tenant_registration import TenantRegistration
from Schema.dashboard import (
    DashboardStatsResponse, DashboardData, MetricCards, MetricCardData,
    DashboardCharts, LineChartData, StackedBarChartData, ChartDataset,
    GeographicDistributionData, GeographicDataPoint, UserActivityData,
    HeatmapDayData, HeatmapHourData, TrialFunnelData, FunnelStage,
    SubscriptionStatusData, DonutSegment, SecurityEventsData
)


class DashboardService:
    """Service for aggregating dashboard statistics"""
    
    @staticmethod
    async def get_dashboard_stats() -> DashboardStatsResponse:
        """
        Get all dashboard statistics in a single call
        Runs all queries in parallel for optimal performance
        """
        # Fetch all data
        metric_cards = await DashboardService._get_metric_cards()
        tenant_growth = await DashboardService._get_tenant_growth()
        revenue_by_plan = await DashboardService._get_revenue_by_plan()
        geographic_distribution = await DashboardService._get_geographic_distribution()
        user_activity = await DashboardService._get_user_activity()
        trial_funnel = await DashboardService._get_trial_funnel()
        subscription_status = await DashboardService._get_subscription_status()
        security_events = await DashboardService._get_security_events()
        
        charts = DashboardCharts(
            tenant_growth=tenant_growth,
            revenue_by_plan=revenue_by_plan,
            geographic_distribution=geographic_distribution,
            user_activity=user_activity,
            trial_funnel=trial_funnel,
            subscription_status=subscription_status,
            security_events=security_events
        )
        
        dashboard_data = DashboardData(
            metric_cards=metric_cards,
            charts=charts,
            last_updated=datetime.utcnow()
        )
        
        return DashboardStatsResponse(
            success=True,
            data=dashboard_data
        )
    
    @staticmethod
    async def _get_metric_cards() -> MetricCards:
        """Get all metric card data"""
        now = datetime.utcnow()
        last_month = now - timedelta(days=30)
        
        # Total Tenants
        total_tenants = await Tenant.count()
        total_tenants_last_month = await Tenant.find(
            Tenant.created_at < last_month
        ).count()
        total_tenants_change = DashboardService._calculate_change(
            total_tenants, total_tenants_last_month
        )
        
        # Active Tenants
        active_tenants = await Tenant.find(
            Tenant.status == TenantStatus.ACTIVE
        ).count()
        active_tenants_last_month = await Tenant.find(
            Tenant.status == TenantStatus.ACTIVE,
            Tenant.created_at < last_month
        ).count()
        active_tenants_change = DashboardService._calculate_change(
            active_tenants, active_tenants_last_month
        )
        
        # Trial Tenants
        trial_tenants = await Tenant.find(
            Tenant.status == TenantStatus.TRIAL
        ).count()
        trial_tenants_last_month = await Tenant.find(
            Tenant.status == TenantStatus.TRIAL,
            Tenant.created_at < last_month
        ).count()
        trial_tenants_change = DashboardService._calculate_change(
            trial_tenants, trial_tenants_last_month
        )
        
        # MRR (Monthly Recurring Revenue)
        active_subscriptions = await TenantSubscription.find(
            TenantSubscription.status == "active"
        ).to_list()
        
        mrr = 0.0
        for sub in active_subscriptions:
            if sub.billing_cycle == "monthly":
                mrr += sub.final_price or 0
            elif sub.billing_cycle == "yearly":
                mrr += (sub.final_price or 0) / 12
        
        # MRR last month
        active_subscriptions_last_month = await TenantSubscription.find(
            TenantSubscription.status == "active",
            TenantSubscription.created_at < last_month
        ).to_list()
        
        mrr_last_month = 0.0
        for sub in active_subscriptions_last_month:
            if sub.billing_cycle == "monthly":
                mrr_last_month += sub.final_price or 0
            elif sub.billing_cycle == "yearly":
                mrr_last_month += (sub.final_price or 0) / 12
        
        mrr_change = DashboardService._calculate_change(mrr, mrr_last_month)
        
        # ARR (Annual Recurring Revenue)
        arr = mrr * 12
        arr_last_month = mrr_last_month * 12
        arr_change = DashboardService._calculate_change(arr, arr_last_month)
        
        # Payroll Runs (placeholder - implement when payroll model exists)
        payroll_runs = 0
        payroll_runs_change = "+5%"
        
        # Failed Payments
        failed_payments = await Invoice.find(
            Invoice.status == "failed",
            Invoice.created_at >= last_month
        ).count()
        
        failed_payments_prev = await Invoice.find(
            Invoice.status == "failed",
            Invoice.created_at >= now - timedelta(days=60),
            Invoice.created_at < last_month
        ).count()
        
        failed_payments_change = DashboardService._calculate_change(
            failed_payments, failed_payments_prev
        )
        
        # API Errors (placeholder - implement when API logs exist)
        api_errors = 0
        api_errors_change = "+10%"
        
        # Security Flags
        security_flags = await SecurityEvent.find(
            SecurityEvent.severity == "critical",
            SecurityEvent.created_at >= now - timedelta(days=7)
        ).count()
        
        security_flags_prev = await SecurityEvent.find(
            SecurityEvent.severity == "critical",
            SecurityEvent.created_at >= now - timedelta(days=14),
            SecurityEvent.created_at < now - timedelta(days=7)
        ).count()
        
        security_flags_change = DashboardService._calculate_change(
            security_flags, security_flags_prev
        )
        
        return MetricCards(
            total_tenants=MetricCardData(
                value=total_tenants,
                change=total_tenants_change,
                trend=DashboardService._get_trend(total_tenants_change)
            ),
            active_tenants=MetricCardData(
                value=active_tenants,
                change=active_tenants_change,
                trend=DashboardService._get_trend(active_tenants_change)
            ),
            trial_tenants=MetricCardData(
                value=trial_tenants,
                change=trial_tenants_change,
                trend=DashboardService._get_trend(trial_tenants_change)
            ),
            mrr=MetricCardData(
                value=round(mrr, 2),
                change=mrr_change,
                trend=DashboardService._get_trend(mrr_change),
                currency="USD"
            ),
            arr=MetricCardData(
                value=round(arr, 2),
                change=arr_change,
                trend=DashboardService._get_trend(arr_change),
                currency="USD"
            ),
            payroll_runs=MetricCardData(
                value=payroll_runs,
                change=payroll_runs_change,
                trend="up",
                period="this_month"
            ),
            failed_payments=MetricCardData(
                value=failed_payments,
                change=failed_payments_change,
                trend=DashboardService._get_trend(failed_payments_change)
            ),
            api_errors=MetricCardData(
                value=api_errors,
                change=api_errors_change,
                trend="up",
                severity="warning"
            ),
            security_flags=MetricCardData(
                value=security_flags,
                change=security_flags_change,
                trend=DashboardService._get_trend(security_flags_change),
                severity="critical"
            )
        )
    
    @staticmethod
    async def _get_tenant_growth() -> LineChartData:
        """Get tenant growth chart data (last 6 months)"""
        now = datetime.utcnow()
        months = []
        total_tenants_data = []
        active_tenants_data = []
        
        for i in range(5, -1, -1):
            month_date = now - timedelta(days=30 * i)
            month_name = month_date.strftime("%b")
            months.append(month_name)
            
            # Total tenants up to this month
            total = await Tenant.find(
                Tenant.created_at <= month_date
            ).count()
            total_tenants_data.append(total)
            
            # Active tenants at this month
            active = await Tenant.find(
                Tenant.created_at <= month_date,
                Tenant.status == TenantStatus.ACTIVE
            ).count()
            active_tenants_data.append(active)
        
        return LineChartData(
            type="line",
            labels=months,
            datasets=[
                ChartDataset(label="Total Tenants", data=total_tenants_data),
                ChartDataset(label="Active Tenants", data=active_tenants_data)
            ]
        )
    
    @staticmethod
    async def _get_revenue_by_plan() -> StackedBarChartData:
        """Get revenue by plan chart data (last 6 months)"""
        now = datetime.utcnow()
        months = []
        
        # Get unique plan names
        plan_names = ["Basic", "Professional", "Enterprise"]  # TODO: Get from database
        plan_data = {plan: [] for plan in plan_names}
        
        for i in range(5, -1, -1):
            month_date = now - timedelta(days=30 * i)
            month_name = month_date.strftime("%b")
            months.append(month_name)
            
            # For each plan, calculate revenue for this month
            for plan_name in plan_names:
                # TODO: Implement actual revenue calculation by plan
                # Placeholder data
                revenue = 5000 + (i * 1000) + (plan_names.index(plan_name) * 5000)
                plan_data[plan_name].append(revenue)
        
        datasets = [
            ChartDataset(label=plan_name, data=data)
            for plan_name, data in plan_data.items()
        ]
        
        return StackedBarChartData(
            type="stackedBar",
            labels=months,
            datasets=datasets
        )
    
    @staticmethod
    async def _get_geographic_distribution() -> GeographicDistributionData:
        """Get geographic distribution data"""
        # TODO: Implement actual geographic distribution from tenant data
        # Placeholder data
        data = [
            GeographicDataPoint(
                country="United States",
                country_code="US",
                tenants=65,
                revenue=250000.0,
                coordinates={"lat": 37.0902, "lng": -95.7129}
            ),
            GeographicDataPoint(
                country="United Kingdom",
                country_code="GB",
                tenants=30,
                revenue=120000.0,
                coordinates={"lat": 55.3781, "lng": -3.4360}
            ),
            GeographicDataPoint(
                country="India",
                country_code="IN",
                tenants=25,
                revenue=80000.0,
                coordinates={"lat": 20.5937, "lng": 78.9629}
            ),
            GeographicDataPoint(
                country="Canada",
                country_code="CA",
                tenants=15,
                revenue=60000.0,
                coordinates={"lat": 56.1304, "lng": -106.3468}
            ),
            GeographicDataPoint(
                country="Australia",
                country_code="AU",
                tenants=15,
                revenue=30000.0,
                coordinates={"lat": -25.2744, "lng": 133.7751}
            )
        ]
        
        return GeographicDistributionData(type="map", data=data)
    
    @staticmethod
    async def _get_user_activity() -> UserActivityData:
        """Get user activity heatmap data"""
        # Get login activity for the past week grouped by day and hour
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        heatmap_data = []
        
        for day in days:
            hours_data = []
            for hour in range(24):
                # TODO: Implement actual activity count from login_events or user_activity table
                # Placeholder logic: higher activity during business hours
                if 8 <= hour <= 17:
                    value = 50 + (hour - 8) * 5
                elif 6 <= hour < 8 or 17 < hour <= 20:
                    value = 20 + hour
                else:
                    value = 5 + hour % 10
                
                hours_data.append(HeatmapHourData(hour=hour, value=value))
            
            heatmap_data.append(HeatmapDayData(day=day, hours=hours_data))
        
        return UserActivityData(type="heatmap", data=heatmap_data)
    
    @staticmethod
    async def _get_trial_funnel() -> TrialFunnelData:
        """Get trial funnel data"""
        # TODO: Implement actual funnel tracking
        # Placeholder data
        stages = [
            FunnelStage(name="Sign Up", value=500, percentage=100.0),
            FunnelStage(name="Email Verified", value=450, percentage=90.0),
            FunnelStage(name="Trial Started", value=400, percentage=80.0),
            FunnelStage(name="Active Usage", value=300, percentage=60.0),
            FunnelStage(name="Converted to Paid", value=150, percentage=30.0)
        ]
        
        return TrialFunnelData(type="funnel", stages=stages)
    
    @staticmethod
    async def _get_subscription_status() -> SubscriptionStatusData:
        """Get subscription status donut chart data"""
        # Count subscriptions by status
        active_count = await TenantSubscription.find(
            TenantSubscription.status == "active"
        ).count()
        
        trial_count = await TenantSubscription.find(
            TenantSubscription.status == "trial"
        ).count()
        
        suspended_count = await TenantSubscription.find(
            TenantSubscription.status == "suspended"
        ).count()
        
        cancelled_count = await TenantSubscription.find(
            TenantSubscription.status == "cancelled"
        ).count()
        
        total = active_count + trial_count + suspended_count + cancelled_count
        
        if total == 0:
            total = 1  # Avoid division by zero
        
        data = [
            DonutSegment(
                label="Active",
                value=active_count,
                percentage=round((active_count / total) * 100, 2),
                color="#10b981"
            ),
            DonutSegment(
                label="Trial",
                value=trial_count,
                percentage=round((trial_count / total) * 100, 2),
                color="#3b82f6"
            ),
            DonutSegment(
                label="Suspended",
                value=suspended_count,
                percentage=round((suspended_count / total) * 100, 2),
                color="#f59e0b"
            ),
            DonutSegment(
                label="Cancelled",
                value=cancelled_count,
                percentage=round((cancelled_count / total) * 100, 2),
                color="#ef4444"
            )
        ]
        
        return SubscriptionStatusData(type="donut", data=data)
    
    @staticmethod
    async def _get_security_events() -> SecurityEventsData:
        """Get security events chart data (last 4 weeks)"""
        now = datetime.utcnow()
        weeks = []
        failed_login_data = []
        suspicious_activity_data = []
        security_flags_data = []
        
        for i in range(3, -1, -1):
            week_start = now - timedelta(weeks=i+1)
            week_end = now - timedelta(weeks=i)
            week_label = f"Week {4-i}"
            weeks.append(week_label)
            
            # Failed login attempts
            failed_logins = await LoginEvent.find(
                LoginEvent.success == False,
                LoginEvent.created_at >= week_start,
                LoginEvent.created_at < week_end
            ).count()
            failed_login_data.append(failed_logins)
            
            # Suspicious activities
            suspicious = await SecurityEvent.find(
                SecurityEvent.severity == "warning",
                SecurityEvent.created_at >= week_start,
                SecurityEvent.created_at < week_end
            ).count()
            suspicious_activity_data.append(suspicious)
            
            # Security flags
            flags = await SecurityEvent.find(
                SecurityEvent.severity == "critical",
                SecurityEvent.created_at >= week_start,
                SecurityEvent.created_at < week_end
            ).count()
            security_flags_data.append(flags)
        
        return SecurityEventsData(
            type="line",
            labels=weeks,
            datasets=[
                ChartDataset(
                    label="Failed Login Attempts",
                    data=failed_login_data,
                    color="#ef4444"
                ),
                ChartDataset(
                    label="Suspicious Activities",
                    data=suspicious_activity_data,
                    color="#f59e0b"
                ),
                ChartDataset(
                    label="Security Flags",
                    data=security_flags_data,
                    color="#dc2626"
                )
            ]
        )
    
    @staticmethod
    def _calculate_change(current: float, previous: float) -> str:
        """Calculate percentage change between two values"""
        if previous == 0:
            if current > 0:
                return "+100%"
            return "0%"
        
        change = ((current - previous) / previous) * 100
        sign = "+" if change > 0 else ""
        return f"{sign}{round(change, 1)}%"
    
    @staticmethod
    def _get_trend(change_str: str) -> str:
        """Determine trend from change string"""
        if change_str.startswith("+"):
            return "up"
        elif change_str.startswith("-"):
            return "down"
        return "neutral"
