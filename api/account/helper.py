import random
from django.contrib.auth import get_user_model
import os
import uuid
from ninja.files import UploadedFile
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.exceptions import ValidationError
from ninja.errors import HttpError

from datetime import timedelta
import random
from datetime import datetime
from django.core.mail import send_mail
# Define allowed image formats
ALLOWED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".gif", ".pdf"]


def generate_unique_username():
    User = get_user_model()
    while True:
        # Generate a random 10-digit number
        username = str(
            random.randint(10**9, 10**10 - 1)
        )  # Generates a number between 1000000000 and 9999999999
        # Check if the username is unique
        if not User.objects.filter(username=username).exists():
            return username


def generate_unique_filename(instance, filename):
    # Extract the file extension
    ext = os.path.splitext(filename)[1]
    # Generate a unique name using UUID
    unique_name = f"{uuid.uuid4()}{ext}"
    return os.path.join("selfie/", unique_name)


def save_uploaded_file(file: UploadedFile, subdirectory: str) -> str:
    """
    Save an uploaded file to the specified subdirectory with a unique name.
    Validates that the file is an image with an allowed format.
    Returns the relative path to the saved file.
    """
    # Extract the file extension
    ext = os.path.splitext(file.name)[1].lower()  # Convert to lowercase for consistency

    # Validate the file format
    if ext not in ALLOWED_IMAGE_FORMATS:
        raise HttpError(
            400,
            f"Unsupported file format. Allowed formats are: {', '.join(ALLOWED_IMAGE_FORMATS)}",
        )

    # Generate a unique name for the file
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(subdirectory, unique_name)
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # Write the file to the media directory
    with open(full_path, "wb+") as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    return file_path


def save_uploaded_file_x(file: UploadedFile, subdirectory: str) -> str:
    """
    Save an uploaded file to the specified subdirectory with a unique name.
    Returns the relative path to the saved file.
    """
    ext = os.path.splitext(file.name)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(subdirectory, unique_name)
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # Write the file to the media directory
    with default_storage.open(full_path, "wb+") as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    return file_path


def email_sender(user, email):
    from .models import EmailValidation
    # Clear any existing OTP for this email
    EmailValidation.objects.filter(email=email).delete()

    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=45)

    EmailValidation.objects.create(
        email=email,
        code=otp_code,
        expires_at=expires_at
    )

    plain_message = (
    f"Hello {user.fullName or 'there'},\n\n"
    f"Welcome to G1 Data!\n"
    f"Your One-Time Password (OTP) is: {otp_code}\n\n"
    "Use this OTP to complete your login or registration on G1 Data. "
    "This OTP will expire in 45 minutes.\n\n"
    "G1 Data – Cheap Data Plans, Airtime & Exam Scratch Cards."
)

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #f3f4f6; padding: 25px;">

    <div style="max-width: 600px; margin: auto; background: white; padding: 30px;
                border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

        <div style="text-align: center;">
            <h2 style="color: #1f2937; margin-bottom: 5px;">
                G1 Data
            </h2>
            <p style="color: #555; font-size: 14px; margin-top: 0;">
                Cheap Data Plans • Airtime • Exam Scratch Cards
            </p>
            <hr style="border: none; height: 1px; background: #e5e7eb; margin: 20px 0;">
        </div>

        <p style="font-size: 16px; color: #333;">
            Hello {user.fullName or 'there'},
        </p>

        <p style="font-size: 15px; color: #444; line-height: 1.6;">
            Welcome to <strong>G1 Data</strong> — your reliable platform for
            affordable data plans, instant airtime recharge, and genuine exam scratch cards.
        </p>

        <p style="font-size: 15px; color: #444; line-height: 1.6;">
            We provide fast delivery, secure transactions, and the best prices to keep you connected
            without stress.
        </p>

        <p style="font-size: 15px; margin-top: 25px; color: #333;">
            Use the <strong>One-Time Password (OTP)</strong> below to continue:
        </p>

        <div style="
            font-size: 26px;
            font-weight: bold;
            background: #eef2ff;
            padding: 15px 20px;
            text-align: center;
            border-radius: 6px;
            letter-spacing: 4px;
            color: #1f2937;
            margin-bottom: 20px;
            border: 1px solid #c7d2fe;
        ">
            {otp_code}
        </div>

        <p style="font-size: 15px; color: #444; line-height: 1.6;">
            <strong>How to proceed:</strong><br>
            1. Visit the G1 Data platform.<br>
            2. Enter the OTP when prompted.<br>
            3. Complete your registration or login.<br><br>
            <em>This OTP is valid for 45 minutes.</em>
        </p>

        <p style="font-size: 14px; color: #666; margin-top: 25px; line-height: 1.6;">
            If you did not request this OTP, please ignore this message.
        </p>

        <p style="font-size: 15px; color: #333; margin-top: 20px;">
            Regards,<br>
            <strong>G1 Data Team</strong>
        </p>

    </div>

    </body>
    </html>
    """

    send_mail(
        subject="G1 Data Management Account OTP Verification",
        message=plain_message,
        html_message=html_message,
        from_email="noreply@g1data.com",
        recipient_list=[email],
        fail_silently=False,
    )


def email_sender_transaction_pin(user, email):
    from .models import EmailValidation
    
    # Clear any existing OTP for this email
    EmailValidation.objects.filter(email=email).delete()

    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=45)

    EmailValidation.objects.create(
        email=email,
        code=otp_code,
        expires_at=expires_at
    )

    plain_message = (
        f"Hello {user.fullName or 'there'},\n\n"
        f"G1 Data Transaction PIN Verification\n\n"
        f"Your One-Time Password (OTP) for setting or resetting your Transaction PIN is: {otp_code}\n\n"
        "Use this OTP to complete your Transaction PIN process on G1 Data. "
        "This OTP will expire in 45 minutes.\n\n"
        "If you did not request this, please ignore this message.\n\n"
        "G1 Data – Cheap Data Plans, Airtime & Exam Scratch Cards."
    )

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #f3f4f6; padding: 25px;">

    <div style="max-width: 600px; margin: auto; background: white; padding: 30px;
                border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

        <div style="text-align: center;">
            <h2 style="color: #1f2937; margin-bottom: 5px;">
                G1 Data
            </h2>
            <p style="color: #555; font-size: 14px; margin-top: 0;">
                Cheap Data Plans • Airtime • Exam Scratch Cards
            </p>
            <hr style="border: none; height: 1px; background: #e5e7eb; margin: 20px 0;">
        </div>

        <p style="font-size: 16px; color: #333;">
            Hello {user.fullName or 'there'},
        </p>

        <p style="font-size: 15px; color: #444; line-height: 1.6;">
            You requested to set or reset your <strong>Transaction PIN</strong> on 
            <strong>G1 Data</strong>.
        </p>

        <p style="font-size: 15px; margin-top: 25px; color: #333;">
            Use the <strong>One-Time Password (OTP)</strong> below to continue:
        </p>

        <div style="
            font-size: 26px;
            font-weight: bold;
            background: #eef2ff;
            padding: 15px 20px;
            text-align: center;
            border-radius: 6px;
            letter-spacing: 4px;
            color: #1f2937;
            margin-bottom: 20px;
            border: 1px solid #c7d2fe;
        ">
            {otp_code}
        </div>

        <p style="font-size: 15px; color: #444; line-height: 1.6;">
            <strong>How to proceed:</strong><br>
            1. Return to the G1 Data platform.<br>
            2. Enter the OTP when prompted.<br>
            3. Complete your Transaction PIN setup or reset.<br><br>
            <em>This OTP is valid for 45 minutes.</em>
        </p>

        <p style="font-size: 14px; color: #666; margin-top: 25px; line-height: 1.6;">
            If you did not request this Transaction PIN verification, please ignore this message.
        </p>

        <p style="font-size: 15px; color: #333; margin-top: 20px;">
            Regards,<br>
            <strong>G1 Data Team</strong>
        </p>

    </div>

    </body>
    </html>
    """

    send_mail(
        subject="G1 Data Transaction PIN OTP Verification",
        message=plain_message,
        html_message=html_message,
        from_email="noreply@g1data.com",
        recipient_list=[email],
        fail_silently=False,
    )


def get_cookie_domain(request):
    host = request.get_host().split(":")[0].lower()

    if host.endswith("localhost") or host.startswith("127."):
        return None  # required for local dev

    return host

def get_app_type(request):
    """
    Decide which app is calling based on subdomain
    """
    host = request.get_host().split(":")[0].lower()

    if host.startswith("adminapi."):
        return "admin"

    return "client"

def send_account_otp_email(user, email):
    import random
    from datetime import timedelta
    from django.utils import timezone
    from django.core.mail import send_mail
    from .models import EmailValidation

    """
    Sends OTP email for new account verification
    """

    # Remove existing OTPs
    EmailValidation.objects.filter(email=email).delete()

    # Generate OTP
    otp_code = str(random.randint(100000, 999999))
    expires_at = timezone.now() + timedelta(minutes=10)

    # Save OTP
    EmailValidation.objects.create(
        email=email,
        code=otp_code,
        expires_at=expires_at
    )

    # Plain text email
    plain_message = (
        f"Assalamu Alaikum {user.first_name or 'Valued Customer'},\n\n"
        "Welcome to SHABABUL KHAIR HALAL INVESTMENT LTD.\n\n"
        "To complete your account registration, please verify your email address "
        "using the One-Time Password (OTP) below:\n\n"
        f"OTP Code: {otp_code}\n\n"
        "This code will expire in 10 minutes.\n\n"
        "If you did not attempt to create an account, please ignore this email.\n\n"
        "Best regards,\n"
        "SHABABUL KHAIR HALAL INVESTMENT LTD"
    )

    # HTML email
    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background:#f4f6f8; padding:25px;">

    <div style="max-width:600px;margin:auto;background:white;padding:30px;
                border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">

        <div style="text-align:center;">
            <h2 style="color:#1c4a27;margin-bottom:5px;">
                SHABABUL KHAIR HALAL INVESTMENT LTD
            </h2>
            <p style="color:#666;font-size:14px;margin-top:0;">
                Secure Account Verification
            </p>
            <hr style="border:none;height:1px;background:#e5e5e5;margin:20px 0;">
        </div>

        <p style="font-size:16px;color:#333;">
            Assalamu Alaikum <strong>{user.first_name or 'Valued Customer'}</strong>,
        </p>

        <p style="font-size:15px;color:#444;line-height:1.6;">
            Thank you for choosing <strong>SHABABUL KHAIR HALAL INVESTMENT LTD</strong>.
            To complete your account registration, please verify your email address
            using the One-Time Password (OTP) below.
        </p>

        <div style="
            font-size:28px;
            font-weight:bold;
            background:#edf7f0;
            padding:15px;
            text-align:center;
            border-radius:8px;
            letter-spacing:5px;
            color:#1c4a27;
            border:1px solid #cde6d2;
            margin:25px 0;
        ">
            {otp_code}
        </div>

        <p style="font-size:14px;color:#555;">
            This OTP will expire in <strong>10 minutes</strong>.
        </p>

        <p style="font-size:14px;color:#666;margin-top:20px;">
            If you did not attempt to create an account, please ignore this email
            or contact our support team immediately.
        </p>

        <p style="font-size:15px;color:#333;margin-top:25px;">
            Best regards,<br>
            <strong>SHABABUL KHAIR HALAL INVESTMENT LTD</strong>
        </p>

    </div>

    </body>
    </html>
    """

    send_mail(
        subject="Verify Your Account – SHABABUL KHAIR HALAL INVESTMENT LTD",
        message=plain_message,
        html_message=html_message,
        from_email="noreply@shababhalal.com",
        recipient_list=[email],
        fail_silently=False,
    )