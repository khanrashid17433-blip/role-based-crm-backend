import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def get_email_config():
    """Dynamically reload and fetch email configurations from environment"""
    try:
        load_dotenv(override=True)
    except Exception:
        pass
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    try:
        port = int(os.getenv("EMAIL_PORT", "587"))
    except Exception:
        port = 587
    address = os.getenv("EMAIL_ADDRESS")
    pwd = os.getenv("EMAIL_PASSWORD")
    password = pwd.replace(" ", "") if pwd else ""
    use_tls = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
    return host, port, address, password, use_tls

# Legacy global fallbacks
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
try:
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
except Exception:
    EMAIL_PORT = 587
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
pwd = os.getenv("EMAIL_PASSWORD")
EMAIL_PASSWORD = pwd.replace(" ", "") if pwd else ""
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"


class EmailService:
    """Service for sending emails via SMTP"""
    
    @staticmethod
    def send_verification_email(
        to_email: str,
        verification_token: str,
        first_name: str = "User",
        company_name: str = "Your Company"
    ) -> bool:
        """
        Send email verification email
        
        Args:
            to_email: Recipient email address
            verification_token: Plain text verification token
            first_name: User's first name
            company_name: Company name
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Verification URL (update with your frontend URL)
            frontend_url = os.getenv("FRONTEND_URL", " https://bidentate-anathematically-stanley.ngrok-free.dev")
            verification_url = f"{frontend_url}/verify-email?token={verification_token}"
            
            # Email content
            subject = "Verify Your Email - Complete Your Registration"
            
            # HTML version
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 40px; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }}
                    .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
                    .token-box {{ background: white; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; font-family: monospace; font-size: 14px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to Our Platform!</h1>
                    </div>
                    <div class="content">
                        <h2>Hi {first_name},</h2>
                        <p>Thank you for registering <strong>{company_name}</strong> with us! We're excited to have you on board.</p>
                        
                        <p>To complete your registration and activate your account, please verify your email address by clicking the button below:</p>
                        
                        <div style="text-align: center;">
                            <a href="{verification_url}" class="button">Verify Email Address</a>
                        </div>
                        
                        <p><strong>Or copy and paste this link into your browser:</strong></p>
                        <div class="token-box">
                            {verification_url}
                        </div>
                        
                        <h3>What's Next?</h3>
                        <ol>
                            <li>Click the verification button above</li>
                            <li>Complete your onboarding process</li>
                            <li>Start using your 14-day free trial</li>
                        </ol>
                        
                        <p><strong>Note:</strong> This verification link will expire in 48 hours.</p>
                        
                        <p>If you didn't create this account, you can safely ignore this email.</p>
                        
                        <p>Best regards,<br>
                        <strong>The Platform Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>This is an automated message, please do not reply to this email.</p>
                        <p>&copy; 2026 Your Platform. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_content = f"""
            Welcome to Our Platform!
            
            Hi {first_name},
            
            Thank you for registering {company_name} with us! We're excited to have you on board.
            
            To complete your registration and activate your account, please verify your email address by clicking the link below:
            
            {verification_url}
            
            What's Next?
            1. Click the verification link above
            2. Complete your onboarding process
            3. Start using your 14-day free trial
            
            Note: This verification link will expire in 48 hours.
            
            If you didn't create this account, you can safely ignore this email.
            
            Best regards,
            The Platform Team
            
            ---
            This is an automated message, please do not reply to this email.
            © 2026 Your Platform. All rights reserved.
            """
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            
            # Attach both plain text and HTML versions
            message.attach(MIMEText(text_content, "plain"))
            message.attach(MIMEText(html_content, "html"))
            
            # Send email
            if EMAIL_USE_TLS:
                context = ssl.create_default_context()
                with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                    server.starttls(context=context)
                    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                    server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            else:
                with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                    server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Verification email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def send_welcome_email(
        to_email: str,
        first_name: str = "User",
        company_name: str = "Your Company"
    ) -> bool:
        """
        Send welcome email after successful verification
        
        Args:
            to_email: Recipient email address
            first_name: User's first name
            company_name: Company name
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            subject = f"Welcome to the Platform, {first_name}!"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Welcome Aboard, {first_name}! 🎉</h2>
                <p>Your account for <strong>{company_name}</strong> has been successfully activated!</p>
                <p>You can now log in and start exploring all the features.</p>
                <p>Happy to have you with us!</p>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            message.attach(MIMEText(html_content, "html"))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Welcome email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_trial_reminder_email(
        to_email: str,
        first_name: str = "User",
        company_name: str = "Your Company",
        days_remaining: int = 7
    ) -> bool:
        """Send trial expiration reminder email"""
        try:
            subject = f"Your Free Trial for {company_name} is Ending in {days_remaining} Days!"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #4f46e5; border-bottom: 2px solid #eef2f6; padding-bottom: 10px;">Trial Period Ending Soon ⏳</h2>
                    <p>Hi {first_name},</p>
                    <p>We hope you are enjoying your free trial of B2B HRMS for <strong>{company_name}</strong>!</p>
                    <p>This is a quick reminder that your 14-day free trial will expire in <strong>{days_remaining} days</strong>.</p>
                    <p>To ensure uninterrupted access to all platform features, employee databases, attendance, and payroll modules, please configure your payment details and active subscription now.</p>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href=" https://bidentate-anathematically-stanley.ngrok-free.dev/billing" 
                           style="background-color: #4f46e5; color: white; padding: 12px 25px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block;">
                           Configure Payment & Subscribe
                        </a>
                    </div>
                    <p>If you have any questions or need an extension, please contact our support team.</p>
                    <p>Best regards,<br><strong>B2B HRMS Support Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            message.attach(MIMEText(html_content, "html"))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Trial reminder email ({days_remaining} days) sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trial reminder email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_trial_expired_email(
        to_email: str,
        first_name: str = "User",
        company_name: str = "Your Company"
    ) -> bool:
        """Send trial expired email (Soft Lockout)"""
        try:
            subject = f"Your Free Trial for {company_name} Has Expired (Action Required)"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #ea580c; border-bottom: 2px solid #eef2f6; padding-bottom: 10px;">Your Trial Has Expired 🔒</h2>
                    <p>Hi {first_name},</p>
                    <p>The free trial period for <strong>{company_name}</strong> has officially ended.</p>
                    <p>To protect your configurations and business continuity, your tenant has been placed in a <strong>grace period soft-lockout</strong>. You will not be able to access main HR services or run payroll until an active payment is made.</p>
                    <p>Please enter your payment method today to reactivate your workspace and unlock all features immediately.</p>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href=" https://bidentate-anathematically-stanley.ngrok-free.dev/billing" 
                           style="background-color: #ea580c; color: white; padding: 12px 25px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block;">
                           Complete Payment
                        </a>
                    </div>
                    <p>If payment is not completed within 7 days, your account will be fully suspended.</p>
                    <p>Best regards,<br><strong>B2B HRMS Support Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            message.attach(MIMEText(html_content, "html"))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Trial expired email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trial expired email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_trial_suspended_email(
        to_email: str,
        first_name: str = "User",
        company_name: str = "Your Company"
    ) -> bool:
        """Send trial suspended email (Day +7)"""
        try:
            subject = f"CRITICAL: Your B2B HRMS Workspace for {company_name} Has Been Suspended"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #dc2626; border-bottom: 2px solid #eef2f6; padding-bottom: 10px;">Workspace Suspended ⚠️</h2>
                    <p>Hi {first_name},</p>
                    <p>Your B2B HRMS tenant for <strong>{company_name}</strong> has been <strong>suspended</strong> because the 7-day grace period following trial expiration passed without payment.</p>
                    <p>All active sessions are terminated, and access to all administrative, employee, and payroll modules is completely blocked. Your configurations are saved, but must be unlocked by making a payment.</p>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href=" https://bidentate-anathematically-stanley.ngrok-free.dev/billing" 
                           style="background-color: #dc2626; color: white; padding: 12px 25px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block;">
                           Pay Now & Reactivate Workspace
                        </a>
                    </div>
                    <p>Please log in to your billing dashboard or contact Superadmin to resolve this balance immediately.</p>
                    <p>Best regards,<br><strong>B2B HRMS Support Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            message.attach(MIMEText(html_content, "html"))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Trial suspended email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trial suspended email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_trial_converted_email(
        to_email: str,
        first_name: str = "User",
        company_name: str = "Your Company"
    ) -> bool:
        """Send trial converted to paid active email"""
        try:
            subject = f"Thank You! Your Subscription for {company_name} is Now Active 🎉"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #16a34a; border-bottom: 2px solid #eef2f6; padding-bottom: 10px;">Welcome to Paid Plan! 🌟</h2>
                    <p>Hi {first_name},</p>
                    <p>Thank you for subscribing to B2B HRMS for <strong>{company_name}</strong>!</p>
                    <p>We are delighted to confirm that your payment/subscription was successfully processed. Your tenant status has been updated to <strong>Active</strong>, and your workspace is fully unlocked with no trial limitations.</p>
                    <p>Enjoy building a great workplace with our automated attendance, leaves, shift management, and payroll integrations!</p>
                    <p>Best regards,<br><strong>B2B HRMS Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = EMAIL_ADDRESS
            message["To"] = to_email
            message.attach(MIMEText(html_content, "html"))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
            
            logger.info(f"Trial converted email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trial converted email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_custom_email(to_email: str, subject: str, body_text: str) -> bool:
        """Send custom HTML email to a lead"""
        try:
            host, port, address, password, use_tls = get_email_config()
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eef2f6; border-radius: 8px;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h2 style="margin: 0; font-size: 20px;">Message from Sales Team</h2>
                    </div>
                    <div style="padding: 24px; background-color: #ffffff; white-space: pre-wrap;">{body_text}</div>
                    <div style="text-align: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid #eef2f6; color: #888; font-size: 11px;">
                        This email was sent via the B2B HRMS Portal. Please do not reply directly.
                    </div>
                </div>
            </body>
            </html>
            """
            
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = address
            message["To"] = to_email
            
            message.attach(MIMEText(body_text, "plain"))
            message.attach(MIMEText(html_content, "html"))
            
            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(host, port) as server:
                    server.starttls(context=context)
                    server.login(address, password)
                    server.sendmail(address, to_email, message.as_string())
            else:
                with smtplib.SMTP(host, port) as server:
                    server.login(address, password)
                    server.sendmail(address, to_email, message.as_string())
            
            logger.info(f"Custom email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send custom email to {to_email}: {str(e)}", exc_info=True)
            return False


# Convenience function
def send_verification_email(to_email: str, token: str, first_name: str = "User", company_name: str = "Company") -> bool:
    """Send verification email (convenience function)"""
    return EmailService.send_verification_email(to_email, token, first_name, company_name)


def send_welcome_email(to_email: str, first_name: str = "User", company_name: str = "Company") -> bool:
    """Send welcome email (convenience function)"""
    return EmailService.send_welcome_email(to_email, first_name, company_name)


def send_invitation_email(
    to_email: str,
    invitation_url: str,
    invited_by_name: str = "Team",
    role: str = "team member",
    company_name: str = "the platform"
) -> bool:
    """Send team invitation email (convenience function)"""
    try:
        subject = f"You're invited to join {company_name}!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 40px; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>You're Invited!</h1>
                </div>
                <div class="content">
                    <h2>Hello!</h2>
                    <p><strong>{invited_by_name}</strong> has invited you to join <strong>{company_name}</strong> on our platform.</p>
                    
                    <p>Your role will be: <strong>{role.replace('_', ' ').title()}</strong></p>
                    
                    <div style="text-align: center;">
                        <a href="{invitation_url}" class="button">Accept Invitation</a>
                    </div>
                    
                    <p><strong>Or copy and paste this link into your browser:</strong></p>
                    <div style="background: white; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; font-family: monospace; font-size: 14px;">
                        {invitation_url}
                    </div>
                    
                    <p><strong>Note:</strong> This invitation link will expire in 7 days.</p>
                    
                    <p>If you weren't expecting this invitation, you can safely ignore this email.</p>
                    
                    <p>Best regards,<br>
                    <strong>The {company_name} Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated message, please do not reply to this email.</p>
                    <p>&copy; 2026 {company_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        You're Invited!
        
        Hello!
        
        {invited_by_name} has invited you to join {company_name} on our platform.
        
        Your role will be: {role.replace('_', ' ').title()}
        
        Accept the invitation by clicking the link below:
        
        {invitation_url}
        
        Note: This invitation link will expire in 7 days.
        
        If you weren't expecting this invitation, you can safely ignore this email.
        
        Best regards,
        The {company_name} Team
        
        ---
        This is an automated message, please do not reply to this email.
        © 2026 {company_name}. All rights reserved.
        """
        
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        import ssl
        
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = EMAIL_ADDRESS
        message["To"] = to_email
        
        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))
        
        if EMAIL_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls(context=context)
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
        else:
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to_email, message.as_string())
        
        logger.info(f"Invitation email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send invitation email to {to_email}: {str(e)}", exc_info=True)
        return False
