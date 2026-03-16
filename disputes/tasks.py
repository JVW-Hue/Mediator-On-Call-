import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Dispute

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_sms_notification(self, to: str, body: str):
    """Send SMS via Twilio."""
    # Production: always attempt real SMS. Development can print if DEBUG.
    if settings.DEBUG:
        print(f"[SMS DEBUG] To: {to}, Body: {body}")
        return None

    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER):
        logger.error("Twilio not configured; cannot send SMS to %s", to)
        return None

    from twilio.rest import Client
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=body,
        from_=settings.TWILIO_FROM_NUMBER,
        to=to,
    )
    logger.info(f"SMS sent to {to}: {message.sid}")
    return message.sid


@shared_task(bind=True, max_retries=3)
def notify_recipient(self, to: str, body: str):
    """Notify a recipient via WhatsApp if configured, else SMS.
    Tries WhatsApp first if TWILIO_WHATSAPP_NUMBER is set; falls back to SMS.
    """
    # Try WhatsApp first when configured
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_NUMBER:
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
                to=f"whatsapp:{to}",
            )
            logger.info(f"WhatsApp sent to {to}: {message.sid}")
            return message.sid
        except Exception as exc:
            logger.exception("WhatsApp delivery failed for %s: %s", to, exc)

    # Fallback to SMS
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_FROM_NUMBER,
                to=to,
            )
            logger.info(f"SMS sent to {to}: {message.sid}")
            return message.sid
        except Exception as exc:
            logger.exception("SMS delivery failed for %s: %s", to, exc)
            self.retry(exc=exc, countdown=60)
    else:
        logger.error("Twilio not configured; cannot notify %s", to)
    return None


@shared_task(bind=True, max_retries=3)
def send_whatsapp(self, to: str, body: str):
    """Send WhatsApp via Twilio."""
    if settings.DEBUG:
        print(f"[WHATSAPP DEBUG] To: {to}, Body: {body}")
        return None

    if not (
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_WHATSAPP_NUMBER
    ):
        logger.error("Twilio WhatsApp not configured. Set TWILIO_WHATSAPP_NUMBER")
        return None

    from twilio.rest import Client

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    
    message = client.messages.create(
        body=body,
        from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
        to=f"whatsapp:{to}",
    )
    logger.info(f"WhatsApp sent to {to}: {message.sid}")
    return message.sid


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def notify_via_sms_or_email(
    to_phone: str | None,
    to_email: str | None,
    subject: str,
    body: str,
):
    """
    Helper that prefers SMS via Twilio, with email fallback.
    - If phone present and Twilio configured, try SMS.
    - If SMS is not possible or fails, and email present, send email.
    """
    sms_sent = False

    if to_phone and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        try:
            send_sms_notification(to=to_phone, body=body)
            sms_sent = True
        except Exception as exc:
            logger.exception("SMS send failed for %s, will try email: %s", to_phone, exc)
            sms_sent = False

    if not sms_sent and to_email:
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(
                    settings,
                    "DEFAULT_FROM_EMAIL",
                    "no-reply@mediators-on-call.local",
                ),
                recipient_list=[to_email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("Email notification failed for %s: %s", to_email, exc)
            raise


@shared_task
def close_expired_forwarded_disputes():
    """Close disputes forwarded to respondent where 30 days have passed without response."""
    cutoff = timezone.now() - timedelta(days=30)
    qs = Dispute.objects.filter(status="forwarded", token_created_at__lt=cutoff)
    for dispute in qs:
        dispute.status = "closed"
        dispute.save(update_fields=["status"])
        if dispute.applicant_cell:
            notify_recipient.delay(
                to=dispute.applicant_cell,
                body=(
                    "Your mediation request has been closed as the respondent "
                    "did not respond within 30 days."
                ),
            )
        logger.info("Closed expired dispute %s", dispute.id)
