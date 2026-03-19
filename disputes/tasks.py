import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Dispute

logger = logging.getLogger(__name__)


def _get_base_context():
    return {
        "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@probonomediation.co.za"),
        "admin_email": getattr(settings, "ADMIN_EMAIL", "admin@probonomediation.co.za"),
    }


@shared_task(bind=True, max_retries=3)
def send_email_notification(self, to_email: str, subject: str, body: str):
    """Send email notification."""
    if settings.DEBUG:
        print(f"[EMAIL DEBUG] To: {to_email}, Subject: {subject}")
        print(f"Body: {body[:200]}...")
        return None

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@probonomediation.co.za"),
            recipient_list=[to_email],
            fail_silently=False,
        )
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as exc:
        logger.exception(f"Email failed for {to_email}: {exc}")
        self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_message_1_dispute_registered(self, to_email: str, applicant_name: str, case_id: int):
    """MESSAGE 1: After registering your dispute - Confirmation to applicant"""
    subject = f"Thank You for Submitting Your Dispute - Case #{case_id}"
    body = f"""Dear {applicant_name},

Thank you for submitting your dispute. Your information has been received and will be monitored by our team.

We will review your case and contact you shortly with further instructions.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_2_dispute_rejected(self, to_email: str, applicant_name: str, case_id: int):
    """MESSAGE 2: If the registrar decides not to proceed with mediation"""
    subject = f"Your Dispute Cannot Be Mediated - Case #{case_id}"
    body = f"""Dear {applicant_name},

The Registrar had assessed the dispute lodged and decided that your dispute cannot be mediated.

You are welcome to lodge an enquiry to complaints@probonomediation.co.za;

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_3_proceed_mediation(self, to_email: str, applicant_name: str, case_id: int):
    """MESSAGE 3: If the registrar decides to proceed with mediation - To applicant"""
    subject = f"Your Dispute Has Been Accepted - Case #{case_id}"
    body = f"""Dear {applicant_name},

The Registrar had assessed the dispute lodged and decided to proceed with mediation. The dispute lodged will now be forwarded to the Respondent for their response. Mediation can only take place if the Respondent agrees to proceed.

If the Respondent agrees to proceed with mediation, they will then file their defence which will be forwarded to you via email. If the Respondent does not agree, the mediation process cannot continue, the file will be closed, and you will receive an email informing you.

The Respondent will be given 14 working days to respond to the request for mediation.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_4_respondent_invitation(
    self,
    to_email: str,
    respondent_name: str,
    applicant_name: str,
    respond_link: str,
    case_id: int,
):
    """MESSAGE 4: Invitation to respondent to participate in mediation"""
    subject = f"You Have Been Invited to Mediation - Case #{case_id}"
    body = f"""Dear {respondent_name},

The Applicant ({applicant_name}) has lodged a dispute through the Pro Bono Community Mediation platform.

We are a Non-Profit entity that provides the community access to a free platform that assists them in resolving disputes without having to go to Courts or lawyers.

Our mediators are experienced, objective and trained to help the community resolve disputes amicably and as quickly as possible. We focus on building bridges and sorting out disputes before people become involved in bitter and expensive court battles. Courts and lawyers should be your last resort. The mediation process is confidential and what was discussed cannot be used later in Court. The mediator does not make any decisions and only assists the Parties in finding an amicable and acceptable solution. If it is not possible, the mediation ends and the file is closed.

The Applicant has chosen the Pro Bono Mediation platform to resolve the dispute, and you are invited to join and state your case. There are no costs attached to this process. You are free to involve your lawyer.

Click on this link - {respond_link} - to view the dispute that has been lodged by the Applicant.

Once viewed you can proceed to agree to continue and file your defence. Your response will then be forwarded to the Applicant. The Registrar will then appoint a mediator who will then contact the Parties and start with the mediation process. Note all services rendered by the mediator is for free at no cost to all Parties.

You will be granted 14 working days to proceed with mediation. If not, the file will be closed and the Applicant will be advised to follow the legal route to resolve the dispute.

Looking forward in assisting you to resolve the dispute as amicably and quickly as possible.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_5_respondent_declined(self, to_email: str, applicant_name: str, case_id: int):
    """MESSAGE 5: If the respondent decides not to proceed with mediation - To applicant"""
    subject = f"Respondent Did Not Agree to Mediation - Case #{case_id}"
    body = f"""Dear {applicant_name},

The Respondent has failed to agree and file their defence within the 14 day period.

Unfortunately, without their consent we are unable to proceed with mediation. The file has been closed.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_6_respondent_agreed(
    self,
    to_email: str,
    applicant_name: str,
    final_confirm_link: str,
    case_id: int,
):
    """MESSAGE 6: If the respondent decides to proceed with mediation - To applicant"""
    subject = f"Respondent Has Agreed to Mediation - Case #{case_id}"
    body = f"""Dear {applicant_name},

The Respondent has agreed to proceed with the mediation process.

Click on this link - {final_confirm_link} - to view the defence filed by the Respondent.

The Registrar will then appoint a mediator who will then contact the Parties and start with the mediation process. Note all services rendered by the mediator is for free at no cost to all Parties.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_7_assign_mediator(
    self,
    admin_email: str,
    case_id: int,
):
    """MESSAGE 7: Notify admin to assign mediator after both parties agreed"""
    subject = f"Action Required: Assign Mediator - Case #{case_id}"
    body = f"""Dear Registrar,

The Parties have reached an agreement to mediate and have both filed their case.

Please proceed to appoint and allocate a mediator.

Regards,
Admin Team"""
    send_email_notification.delay(admin_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_8_mediator_assigned_mediator(
    self,
    to_email: str,
    mediator_name: str,
    case_id: int,
):
    """MESSAGE 8: Notify mediator of their assignment"""
    subject = f"You Have Been Assigned a Case - Case #{case_id}"
    body = f"""Dear {mediator_name},

Please log into your profile to check the dispute that has been allocated to you.

It is imperative to contact the Parties within 3 working days to make the necessary arrangement to proceed with and finalize the mediation of the matter.

Once finalized log in and note the outcome.

Regards,
Admin Team"""
    send_email_notification.delay(to_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_8_mediator_assigned_parties(
    self,
    applicant_email: str,
    respondent_email: str,
    mediator_name: str,
    case_id: int,
):
    """MESSAGE 8: Notify parties that a mediator has been assigned"""
    subject = f"A Mediator Has Been Assigned - Case #{case_id}"
    body = f"""Dear Applicant / Respondent,

{mediator_name} has been appointed and allocated to mediate the matter and will shortly be in contact to make the necessary arrangements to proceed with the mediation process.

Should you not hear from the mediator within 5 working days after receiving this message please send an email to complaints@probonomediation.co.za.

Best wishes in finding an amicable solution to resolve the dispute.

Regards,
Admin Team"""
    if applicant_email:
        send_email_notification.delay(applicant_email, subject, body)
    if respondent_email:
        send_email_notification.delay(respondent_email, subject, body)


@shared_task(bind=True, max_retries=3)
def send_message_9_outcome_filed(
    self,
    admin_email: str,
    case_id: int,
):
    """MESSAGE 9: Notify admin that outcome has been filed"""
    subject = f"Mediation Outcome Filed - Case #{case_id}"
    body = f"""Dear Registrar,

The matter has been finalized and the outcome has been filed.

Regards,
Admin Team"""
    send_email_notification.delay(admin_email, subject, body)


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
