import html
import logging
import smtplib
import threading
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .config import (
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
    SMTP_FROM_EMAIL, SMTP_USE_TLS,
)

log = logging.getLogger("lapi.web.email")

DURATION_LABELS_FR = {
    "daily": "journalier",
    "weekly": "hebdomadaire",
    "monthly": "mensuel",
    "quarterly": "trimestriel",
    "yearly": "annuel",
}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _ts_to_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%Y")


def _send_email(to: str, subject: str, html_body: str):
    """Send email in a background thread to avoid blocking the request."""
    if not SMTP_HOST:
        log.debug(f"SMTP non configure, email non envoye a {to}: {subject}")
        return

    def _do_send():
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = SMTP_FROM_EMAIL
            msg["To"] = to
            msg["Subject"] = subject

            msg.attach(MIMEText(html_body, "html", "utf-8"))

            if SMTP_USE_TLS:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                server.starttls()
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)

            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, to, msg.as_string())
            server.quit()
            log.info(f"Email envoye a {to}: {subject}")
        except Exception as e:
            log.error(f"Erreur envoi email a {to}: {e}")

    threading.Thread(target=_do_send, daemon=True).start()


def send_payment_confirmation(subscriber, subscription):
    """Email de confirmation de paiement a l'abonne."""
    plan = subscription.plan
    parking = plan.parking
    duration_label = DURATION_LABELS_FR.get(plan.duration.value, plan.duration.value)
    price = f"{plan.price_cents / 100:.2f}"

    first_name = _esc(subscriber.first_name)
    parking_name = _esc(parking.name)
    plan_name = _esc(plan.name)
    plate = _esc(subscriber.plate)

    html_content = f"""\
<html>
<body style="font-family: -apple-system, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto;">
  <div style="background: #2563eb; color: white; padding: 1.5rem; text-align: center;">
    <h1 style="margin: 0; font-size: 1.3rem;">LAPI - Confirmation de paiement</h1>
  </div>
  <div style="padding: 1.5rem; background: #f8fafc; border: 1px solid #e2e8f0;">
    <p>Bonjour {first_name},</p>
    <p>Votre abonnement a bien ete active. Voici le recapitulatif :</p>
    <table style="width: 100%; border-collapse: collapse; margin: 1rem 0;">
      <tr><td style="padding: 0.5rem; color: #64748b;">Parking</td><td style="padding: 0.5rem; font-weight: 600;">{parking_name}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Formule</td><td style="padding: 0.5rem; font-weight: 600;">{plan_name} ({_esc(duration_label)})</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Montant</td><td style="padding: 0.5rem; font-weight: 600;">{_esc(price)} &euro;</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Plaque</td><td style="padding: 0.5rem; font-weight: 600; font-family: monospace;">{plate}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Debut</td><td style="padding: 0.5rem;">{_ts_to_date(subscription.start_date)}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Fin</td><td style="padding: 0.5rem;">{_ts_to_date(subscription.end_date)}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Renouvellement auto</td><td style="padding: 0.5rem;">{"Oui" if subscription.auto_renew else "Non"}</td></tr>
    </table>
    <p>Votre plaque est desormais autorisee sur le parking. L'acces est immediat.</p>
    <p style="color: #64748b; font-size: 0.85rem;">Cet email est un justificatif de paiement. Conservez-le.</p>
  </div>
</body>
</html>"""

    _send_email(
        subscriber.email,
        f"LAPI - Confirmation abonnement {parking.name}",
        html_content,
    )


def send_expiry_warning(subscriber, subscription, days_remaining: int):
    """Email d'avertissement 5 jours avant expiration."""
    plan = subscription.plan
    parking = plan.parking

    first_name = _esc(subscriber.first_name)
    parking_name = _esc(parking.name)
    plan_name = _esc(plan.name)
    plate = _esc(subscriber.plate)

    renew_msg = (
        "Votre abonnement est configure en renouvellement automatique, aucune action n'est requise."
        if subscription.auto_renew
        else "Pensez a renouveler votre abonnement depuis votre espace personnel pour conserver votre acces."
    )

    html_content = f"""\
<html>
<body style="font-family: -apple-system, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto;">
  <div style="background: #f59e0b; color: white; padding: 1.5rem; text-align: center;">
    <h1 style="margin: 0; font-size: 1.3rem;">LAPI - Abonnement bientot expire</h1>
  </div>
  <div style="padding: 1.5rem; background: #f8fafc; border: 1px solid #e2e8f0;">
    <p>Bonjour {first_name},</p>
    <p>Votre abonnement au parking <strong>{parking_name}</strong> expire dans
       <strong>{days_remaining} jour{"s" if days_remaining > 1 else ""}</strong>
       (le {_ts_to_date(subscription.end_date)}).</p>
    <table style="width: 100%; border-collapse: collapse; margin: 1rem 0;">
      <tr><td style="padding: 0.5rem; color: #64748b;">Formule</td><td style="padding: 0.5rem; font-weight: 600;">{plan_name}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Plaque</td><td style="padding: 0.5rem; font-family: monospace;">{plate}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Renouvellement auto</td><td style="padding: 0.5rem;">{"Oui" if subscription.auto_renew else "Non"}</td></tr>
    </table>
    <p>{renew_msg}</p>
    <p style="color: #64748b; font-size: 0.85rem;">Sans renouvellement, votre plaque sera retiree de la whitelist a la date d'expiration.</p>
  </div>
</body>
</html>"""

    _send_email(
        subscriber.email,
        f"LAPI - Votre abonnement {parking.name} expire dans {days_remaining}j",
        html_content,
    )


def send_manager_new_subscription(tenant, subscriber, subscription):
    """Email de notification au gestionnaire de parking lors d'un nouvel abonnement."""
    if not tenant.contact_email:
        log.debug(f"Tenant {tenant.name} n'a pas d'email, notification non envoyee")
        return

    plan = subscription.plan
    parking = plan.parking
    duration_label = DURATION_LABELS_FR.get(plan.duration.value, plan.duration.value)
    price = f"{plan.price_cents / 100:.2f}"

    parking_name = _esc(parking.name)
    first_name = _esc(subscriber.first_name)
    last_name = _esc(subscriber.last_name)
    email = _esc(subscriber.email)
    plate = _esc(subscriber.plate)
    plan_name = _esc(plan.name)

    html_content = f"""\
<html>
<body style="font-family: -apple-system, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto;">
  <div style="background: #16a34a; color: white; padding: 1.5rem; text-align: center;">
    <h1 style="margin: 0; font-size: 1.3rem;">LAPI - Nouvel abonnement</h1>
  </div>
  <div style="padding: 1.5rem; background: #f8fafc; border: 1px solid #e2e8f0;">
    <p>Bonjour,</p>
    <p>Un nouvel abonnement vient d'etre souscrit sur votre parking <strong>{parking_name}</strong>.</p>
    <table style="width: 100%; border-collapse: collapse; margin: 1rem 0;">
      <tr><td style="padding: 0.5rem; color: #64748b;">Abonne</td><td style="padding: 0.5rem; font-weight: 600;">{first_name} {last_name}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Email</td><td style="padding: 0.5rem;">{email}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Plaque</td><td style="padding: 0.5rem; font-family: monospace; font-weight: 600;">{plate}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Formule</td><td style="padding: 0.5rem;">{plan_name} ({_esc(duration_label)})</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Montant</td><td style="padding: 0.5rem; font-weight: 600;">{_esc(price)} &euro;</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Periode</td><td style="padding: 0.5rem;">{_ts_to_date(subscription.start_date)} &rarr; {_ts_to_date(subscription.end_date)}</td></tr>
      <tr><td style="padding: 0.5rem; color: #64748b;">Renouvellement auto</td><td style="padding: 0.5rem;">{"Oui" if subscription.auto_renew else "Non"}</td></tr>
    </table>
    <p>La plaque a ete automatiquement ajoutee a la whitelist de tous les dispositifs du parking.</p>
  </div>
</body>
</html>"""

    _send_email(
        tenant.contact_email,
        f"LAPI - Nouvel abonnement sur {parking.name} ({subscriber.plate})",
        html_content,
    )
