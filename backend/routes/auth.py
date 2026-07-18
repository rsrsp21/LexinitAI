import secrets
import string
import time
import re

from flask import current_app, jsonify, request, session
from flask_mail import Message
from bson import ObjectId
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import mail, mongo
from backend.lexinit.schemas.profile import ProfileType, ProfileUpdateRequest

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)


def generate_verification_code(length=4):
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _request_value(name):
    data = request.get_json(silent=True) if request.is_json else None
    if isinstance(data, dict) and data.get(name) is not None:
        return data.get(name)
    return request.form.get(name)


def _normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else ""


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ""


def _password_value(value):
    return value if isinstance(value, str) else ""


def _validate_email(email):
    if not email:
        return "Enter your email address."
    if len(email) > 254 or not EMAIL_RE.match(email):
        return "Enter a valid email address."
    return None


def _validate_name(name):
    if not isinstance(name, str):
        return "Enter your name."
    if len(name) < 2:
        return "Enter your name."
    if len(name) > 80:
        return "Name must be 80 characters or fewer."
    return None


def _validate_password(password):
    if not isinstance(password, str):
        return "Enter a valid password."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be 128 characters or fewer."
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    return None


def _accepted_terms(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _send_verification_email(email, code):
    if current_app.config.get("MAIL_SUPPRESS_SEND") or not current_app.config.get("MAIL_PASSWORD"):
        print(f"Email sending suppressed. Verification code for {email}: {code}")
        return True, "Verification code generated for local development.", code

    try:
        msg = Message(
            "Verification Code",
            sender=current_app.config["MAIL_USERNAME"],
            recipients=[email],
        )
        msg.body = f"Your verification code is: {code}\nPlease enter this code to complete your registration."
        mail.send(msg)
        return True, "Verification code sent to your email.", None
    except Exception as exc:
        print("Email send error:", exc)
        return False, "Failed to send email. Try again.", None


def _send_password_reset_code(email, code):
    if current_app.config.get("MAIL_SUPPRESS_SEND") or not current_app.config.get("MAIL_PASSWORD"):
        print(f"Email sending suppressed. Password reset code for {email}: {code}")
        return True, "Password reset code generated for local development.", code

    try:
        msg = Message(
            "Lexinit Password Reset Code",
            sender=current_app.config["MAIL_USERNAME"],
            recipients=[email],
        )
        msg.body = (
            f"Your Lexinit password reset code is: {code}\n"
            "Enter this code to set a new password. If you did not request this, you can ignore this email."
        )
        mail.send(msg)
        return True, "Password reset code sent to your email.", None
    except Exception as exc:
        print("Password reset email error:", exc)
        return False, "Failed to send reset code. Try again.", None


def _signup_next_step(draft):
    if not draft or not draft.get("email_verified"):
        return "verify"
    return "password"


PROFILE_FIELD_MESSAGES = {
    "name": "Enter a name between 2 and 80 characters.",
    "profile_type": "Choose student, professional, or independent learner.",
    "institution_name": "Add your school, college, or university name.",
    "grade_or_class": "Add your grade or class.",
    "organization_name": "Add your organization name.",
    "professional_role": "Role or job title must be 120 characters or fewer.",
    "work_experience_years": "Work experience must be a whole number between 0 and 70.",
    "": "Complete the required details for the selected account type.",
}


def _validated_profile(values):
    if not isinstance(values, dict):
        return None, PROFILE_FIELD_MESSAGES[""]
    try:
        return (
            ProfileUpdateRequest.model_validate(
                {
                    "name": values.get("name"),
                    "profile_type": values.get("profile_type"),
                    "institution_name": values.get("institution_name"),
                    "grade_or_class": values.get("grade_or_class"),
                    "organization_name": values.get("organization_name"),
                    "professional_role": values.get("professional_role"),
                    "work_experience_years": values.get("work_experience_years"),
                }
            ),
            None,
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = first_error.get("loc") or ()
        field = str(location[0]) if location else ""
        return None, PROFILE_FIELD_MESSAGES.get(field, PROFILE_FIELD_MESSAGES[""])


def _profile_database_update(profile):
    values = {
        "name": profile.name,
        "profile_type": profile.profile_type.value,
    }
    if profile.profile_type == ProfileType.STUDENT:
        values.update(
            institution_name=profile.institution_name,
            grade_or_class=profile.grade_or_class,
        )
        unset = {"organization_name": "", "professional_role": "", "work_experience_years": ""}
    elif profile.profile_type == ProfileType.PROFESSIONAL:
        values.update(
            organization_name=profile.organization_name,
            professional_role=profile.professional_role,
            work_experience_years=profile.work_experience_years,
        )
        unset = {"institution_name": "", "grade_or_class": ""}
    else:
        unset = {
            "institution_name": "",
            "grade_or_class": "",
            "organization_name": "",
            "professional_role": "",
            "work_experience_years": "",
        }
    return values, unset


def _active_signup_draft(email):
    draft = mongo.db.user_verify.find_one({"email": email, "signup_flow": "staged"})  # type: ignore
    if not draft:
        return None
    if draft.get("signup_expires_at", 0) < time.time():
        mongo.db.user_verify.delete_one({"email": email, "signup_flow": "staged"})
        return None
    return draft


def _active_password_reset(email):
    reset = mongo.db.password_resets.find_one({"email": email})  # type: ignore
    if not reset:
        return None
    if reset.get("reset_expires_at", 0) < time.time():
        mongo.db.password_resets.delete_one({"email": email})
        return None
    return reset


def _signed_in_user():
    user_id = session.get("user_id")
    try:
        return mongo.db.users.find_one({"_id": ObjectId(user_id)}) if user_id else None
    except Exception:
        return None


def register_routes(app):
    @app.route("/api/v1/account/password/start", methods=["POST"])
    def start_password_change():
        user = _signed_in_user()
        if not user:
            return jsonify(success=False, message="User not logged in."), 401
        now = time.time()
        existing = mongo.db.password_change_codes.find_one({"user_id": user["_id"]})
        if existing and existing.get("expires_at", 0) > now and now - existing.get("sent_at", 0) < 30:
            return jsonify(success=False, message="Please wait before requesting another code."), 429
        code = generate_verification_code()
        mongo.db.password_change_codes.update_one(
            {"user_id": user["_id"]},
            {"$set": {"user_id": user["_id"], "code": code, "sent_at": now, "expires_at": now + 600, "verified": False, "attempts": 0}},
            upsert=True,
        )
        sent, message, dev_code = _send_password_reset_code(user["email"], code)
        if not sent:
            return jsonify(success=False, message=message), 503
        response = {"success": True, "message": "A verification code has been sent to your email.", "expires_in": 600}
        if dev_code:
            response["verification_code"] = dev_code
        return jsonify(response)

    @app.route("/api/v1/account/password/verify", methods=["POST"])
    def verify_password_change():
        user = _signed_in_user()
        code = _clean_text(_request_value("code"))
        if not user:
            return jsonify(success=False, message="User not logged in."), 401
        record = mongo.db.password_change_codes.find_one({"user_id": user["_id"]})
        if not record or record.get("expires_at", 0) < time.time():
            return jsonify(success=False, message="Code expired. Request a new one."), 400
        if not code.isdigit() or len(code) != 4:
            return jsonify(success=False, message="Enter the 4-digit verification code."), 400
        if record.get("attempts", 0) >= 5:
            return jsonify(success=False, message="Too many attempts. Request a new code."), 429
        if record.get("code") != code:
            mongo.db.password_change_codes.update_one({"_id": record["_id"]}, {"$inc": {"attempts": 1}})
            return jsonify(success=False, message="Incorrect code."), 400
        mongo.db.password_change_codes.update_one({"_id": record["_id"]}, {"$set": {"verified": True}})
        return jsonify(success=True, message="Code verified.")

    @app.route("/api/v1/account/password/complete", methods=["POST"])
    def complete_password_change():
        user = _signed_in_user()
        password = _password_value(_request_value("new_password"))
        confirm_password = _password_value(_request_value("confirm_password"))
        if not user:
            return jsonify(success=False, message="User not logged in."), 401
        record = mongo.db.password_change_codes.find_one({"user_id": user["_id"]})
        if not record or not record.get("verified") or record.get("expires_at", 0) < time.time():
            return jsonify(success=False, message="Verify a current code before changing your password."), 400
        error = _validate_password(password)
        if error:
            return jsonify(success=False, message=error), 400
        if password != confirm_password:
            return jsonify(success=False, message="Passwords do not match."), 400
        mongo.db.users.update_one({"_id": user["_id"]}, {"$set": {"password": generate_password_hash(password), "forgot_password": False}})
        mongo.db.password_change_codes.delete_one({"_id": record["_id"]})
        return jsonify(success=True, message="Password updated successfully.")

    @app.route("/auth/signup/start", methods=["POST"])
    def signup_start():
        email = _normalize_email(_request_value("email"))
        resend = str(_request_value("resend") or "").strip().lower() in {"1", "true", "yes"}
        now = time.time()

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error)

        if mongo.db.users.find_one({"email": email}):  # type: ignore
            return jsonify(success=False, message="Email already exists. Please sign in.")

        draft = _active_signup_draft(email)
        if draft and draft.get("email_verified"):
            return jsonify(
                success=True,
                message="Email already verified. Continue signup.",
                next_step=_signup_next_step(draft),
                email=email,
                expires_in=max(0, int(draft.get("signup_expires_at", now) - now)),
            )

        if draft and draft.get("code_expires_at", 0) > now and not resend:
            return jsonify(
                success=True,
                message="Use the verification code already sent.",
                next_step="verify",
                email=email,
                expires_in=max(0, int(draft.get("code_expires_at", now) - now)),
                resend_after=max(
                    0,
                    int(current_app.config["SIGNUP_RESEND_COOLDOWN_SECONDS"] - (now - draft.get("verification_time", 0))),
                ),
            )

        cooldown = current_app.config["SIGNUP_RESEND_COOLDOWN_SECONDS"]
        if draft and now - draft.get("verification_time", 0) < cooldown:
            resend_after = int(cooldown - (now - draft.get("verification_time", 0)))
            return jsonify(
                success=False,
                message=f"Please wait {resend_after}s before requesting another code.",
                resend_after=resend_after,
            )

        code = generate_verification_code()
        otp_ttl = current_app.config["SIGNUP_OTP_TTL_SECONDS"]
        draft_ttl = current_app.config["SIGNUP_DRAFT_TTL_SECONDS"]
        mongo.db.user_verify.update_one(
            {"email": email},
            {
                "$set": {
                    "email": email,
                    "signup_flow": "staged",
                    "verification_code": code,
                    "verification_time": now,
                    "code_expires_at": now + otp_ttl,
                    "signup_expires_at": now + draft_ttl,
                    "email_verified": False,
                    "verified": False,
                    "code_attempts": 0,
                },
                "$unset": {"password": "", "name": ""},
                "$inc": {"resend_count": 1},
            },
            upsert=True,
        )

        sent, message, dev_code = _send_verification_email(email, code)
        if not sent:
            return jsonify(success=False, message=message)

        response = {
            "success": True,
            "message": message,
            "next_step": "verify",
            "email": email,
            "expires_in": otp_ttl,
            "resend_after": cooldown,
        }
        if dev_code:
            response["verification_code"] = dev_code
        return jsonify(response)

    @app.route("/auth/signup/verify", methods=["POST"])
    def signup_verify():
        email = _normalize_email(_request_value("email"))
        code = _clean_text(_request_value("code"))
        now = time.time()

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error, next_step="email")
        if not code:
            return jsonify(success=False, message="Enter the verification code.")
        if not code.isdigit() or len(code) != 4:
            return jsonify(success=False, message="Enter the 4-digit verification code.")

        draft = _active_signup_draft(email)
        if not draft:
            return jsonify(success=False, message="Signup attempt expired. Start again.", next_step="email")

        if draft.get("code_expires_at", 0) < now:
            return jsonify(success=False, message="Code expired. Resend a new code.", next_step="verify", expired=True)

        max_attempts = current_app.config["SIGNUP_MAX_CODE_ATTEMPTS"]
        if draft.get("code_attempts", 0) >= max_attempts:
            return jsonify(success=False, message="Too many attempts. Resend a new code.", next_step="verify")

        if draft.get("verification_code") != code:
            attempts = draft.get("code_attempts", 0) + 1
            mongo.db.user_verify.update_one({"email": email}, {"$set": {"code_attempts": attempts}})
            remaining = max(0, max_attempts - attempts)
            return jsonify(success=False, message=f"Invalid code. {remaining} attempts left.", attempts_left=remaining)

        mongo.db.user_verify.update_one(
            {"email": email},
            {
                "$set": {
                    "email_verified": True,
                    "verified": True,
                    "verified_at": now,
                    "signup_expires_at": now + current_app.config["SIGNUP_DRAFT_TTL_SECONDS"],
                },
                "$unset": {"verification_code": ""},
            },
        )
        return jsonify(success=True, message="Email verified.", next_step="password")

    @app.route("/auth/signup/profile", methods=["POST"])
    def signup_profile():
        email = _normalize_email(_request_value("email"))
        draft = _active_signup_draft(email)

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error, next_step="email")
        if not draft or not draft.get("email_verified"):
            return jsonify(success=False, message="Verify your email first.", next_step="email")
        profile, profile_error = _validated_profile(
            {
                "name": _clean_text(_request_value("name")),
                "profile_type": _clean_text(_request_value("profile_type")),
                "institution_name": _clean_text(_request_value("institution_name")) or None,
                "grade_or_class": _clean_text(_request_value("grade_or_class")) or None,
                "organization_name": _clean_text(_request_value("organization_name")) or None,
                "professional_role": _clean_text(_request_value("professional_role")) or None,
                "work_experience_years": _request_value("work_experience_years"),
            }
        )
        if not profile:
            return jsonify(success=False, message=profile_error, next_step="profile")

        profile_values, profile_unset = _profile_database_update(profile)

        mongo.db.user_verify.update_one(
            {"email": email},
            {
                "$set": {
                    **profile_values,
                    "signup_expires_at": time.time() + current_app.config["SIGNUP_DRAFT_TTL_SECONDS"],
                },
                "$unset": profile_unset,
            },
        )
        return jsonify(success=True, message="Profile saved.", next_step="password")

    @app.route("/auth/signup/complete", methods=["POST"])
    def signup_complete():
        email = _normalize_email(_request_value("email"))
        password = _password_value(_request_value("password"))
        confirm_password = _password_value(_request_value("confirm_password"))
        agreed_terms = _accepted_terms(_request_value("agreed_terms"))
        agreed_privacy = _accepted_terms(_request_value("agreed_privacy"))
        draft = _active_signup_draft(email)

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error, next_step="email")
        if not draft or not draft.get("email_verified"):
            return jsonify(success=False, message="Verify your email first.", next_step="email")
        password_error = _validate_password(password)
        if password_error:
            return jsonify(success=False, message=password_error)
        if password != confirm_password:
            return jsonify(success=False, message="Passwords do not match.")
        if not agreed_terms or not agreed_privacy:
            return jsonify(
                success=False,
                message="You must agree to the Terms of Service and Privacy Policy to create an account.",
                next_step="terms",
            )
        if mongo.db.users.find_one({"email": email}):  # type: ignore
            mongo.db.user_verify.delete_one({"email": email})
            return jsonify(success=False, message="Email already exists. Please sign in.", next_step="signin")

        now = time.time()
        result = mongo.db.users.insert_one(
            {
                "email": email,
                "password": generate_password_hash(password),
                "verified": True,
                "profile_complete": False,
                "agreed_terms": True,
                "terms_accepted_at": now,
                "agreed_privacy": True,
                "privacy_accepted_at": now,
                "legal_version": "2026-07-19",
                "plan": "free",
                "rate_limit": 0,
                "deep_rate_limit": 0,
            }
        )
        mongo.db.user_verify.delete_one({"email": email})
        session.permanent = True
        session["user_id"] = str(result.inserted_id)
        return jsonify(success=True, message="Account created.", next_step="app", redirect_url="/app")

    @app.route("/send-code", methods=["POST"])
    def send_code():
        email = _normalize_email(request.form.get("signup-email"))
        name = _clean_text(request.form.get("full-name"))
        password = request.form.get("signup-password")
        agreed_terms = request.form.get("agreed_terms")

        if not email or not name or not password:
            return jsonify(success=False, message="Please fill all signup fields.")
        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error)
        name_error = _validate_name(name)
        if name_error:
            return jsonify(success=False, message=name_error)
        password_error = _validate_password(password)
        if password_error:
            return jsonify(success=False, message=password_error)

        if agreed_terms != "yes":
            return jsonify(success=False, message="You must agree to the Terms of Service and Privacy Policy to sign up.")

        if mongo.db.users.find_one({"email": email}):  # type: ignore
            return jsonify(success=False, message="Email already exists. Please login.")

        temp_code = generate_verification_code()
        hashed_password = generate_password_hash(password)
        now = time.time()

        mongo.db.user_verify.update_one(
            {"email": email},
            {
                "$set": {
                    "email": email,
                    "name": name,
                    "password": hashed_password,
                    "verification_code": temp_code,
                    "verification_time": now,
                    "verified": False,
                    "agreed_terms": True,
                }
            },
            upsert=True,
        )

        if current_app.config.get("MAIL_SUPPRESS_SEND") or not current_app.config.get("MAIL_PASSWORD"):
            print(f"Email sending suppressed. Verification code for {email}: {temp_code}")
            return jsonify(
                success=True,
                message="Verification code generated for local development.",
                verification_code=temp_code,
            )

        try:
            msg = Message(
                "Verification Code",
                sender=current_app.config["MAIL_USERNAME"],
                recipients=[email],
            )
            msg.body = f"Your verification code is: {temp_code}\nPlease enter this code to complete your registration."
            mail.send(msg)
        except Exception as exc:
            print("Email send error:", exc)
            return jsonify(success=False, message="Failed to send email. Try again.")

        return jsonify(success=True, message="Verification code sent to your email.")

    @app.route("/verify-code", methods=["POST"])
    def verify_code():
        email = _normalize_email(request.form.get("signup-email"))
        code = _clean_text(request.form.get("verification-code"))

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error)
        if not code:
            return jsonify(success=False, message="Please enter the verification code.")

        user = mongo.db.user_verify.find_one({"email": email})  # type: ignore

        if not user:
            return jsonify(success=False, message="No signup attempt found. Please sign up again.")
        if user["verified"]:
            return jsonify(success=False, message="This email is already verified. Please log in.")
        if user["verification_code"] != code:
            return jsonify(success=False, message="Invalid verification code. Please try again.")

        if time.time() - user["verification_time"] > 60 * 1:
            mongo.db.user_verify.delete_one({"email": email})
            return jsonify(success=False, message="Verification code expired. Please sign up again.")

        mongo.db.users.insert_one(
            {
                "email": user["email"],
                "name": user["name"],
                "password": user["password"],
                "verified": True,
                "agreed_terms": True,
                "terms_accepted_at": time.time(),
                "plan": "free",
                "rate_limit": 0,
                "deep_rate_limit": 0,
            }
        )
        mongo.db.user_verify.delete_one({"email": email})

        return jsonify(success=True, message="Sign Up successful! Please log in.")

    @app.route("/login", methods=["POST"])
    def login():
        email = _normalize_email(request.form.get("login-email"))
        password = request.form.get("login-password")

        if not email or not password:
            return jsonify(success=False, message="Please enter email and password.")
        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error)

        user = mongo.db.users.find_one({"email": email})  # type: ignore

        if user and check_password_hash(user["password"], password) and user["verified"]:
            if user.get("forgot_password"):
                mongo.db.users.update_one(
                    {"_id": user["_id"]},
                    {
                        "$set": {"forgot_password": False},
                        "$unset": {
                            "temp_password": "",
                            "temp_password_created_at": "",
                            "temp_password_expires_at": "",
                        },
                    },
                )
                mongo.db.password_resets.delete_one({"email": email})
            session.permanent = True
            session["user_id"] = str(user["_id"])
            return jsonify(
                success=True,
                message="Login successful.",
                redirect_url="/dashboard",
            )
        return jsonify(success=False, message="Invalid credentials or unverified account.")

    @app.route("/forgot_password", methods=["POST"])
    @app.route("/api/v1/forgot-password", methods=["POST"])
    @app.route("/api/forgot-password", methods=["POST"])
    def forgot_password():
        email = _normalize_email(_request_value("email"))
        resend = str(_request_value("resend") or "").strip().lower() in {"1", "true", "yes"}
        now = time.time()
        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error), 400

        user = mongo.db.users.find_one({"email": email})
        if not user:
            return jsonify(success=False, message="No account found with that email."), 404

        reset = _active_password_reset(email)
        if reset and reset.get("email_verified"):
            return jsonify(
                success=True,
                message="Code already verified. Set your new password.",
                next_step="password",
                email=email,
                expires_in=max(0, int(reset.get("reset_expires_at", now) - now)),
            )

        if reset and reset.get("code_expires_at", 0) > now and not resend:
            return jsonify(
                success=True,
                message="Use the password reset code already sent.",
                next_step="verify",
                email=email,
                expires_in=max(0, int(reset.get("code_expires_at", now) - now)),
                resend_after=max(
                    0,
                    int(current_app.config["PASSWORD_RESET_RESEND_COOLDOWN_SECONDS"] - (now - reset.get("verification_time", 0))),
                ),
            )

        cooldown = current_app.config["PASSWORD_RESET_RESEND_COOLDOWN_SECONDS"]
        if reset and now - reset.get("verification_time", 0) < cooldown:
            resend_after = int(cooldown - (now - reset.get("verification_time", 0)))
            return jsonify(
                success=False,
                message=f"Please wait {resend_after}s before requesting another code.",
                resend_after=resend_after,
            )

        code = generate_verification_code()
        otp_ttl = current_app.config["PASSWORD_RESET_OTP_TTL_SECONDS"]
        mongo.db.password_resets.update_one(
            {"email": email},
            {
                "$set": {
                    "email": email,
                    "verification_code": code,
                    "verification_time": now,
                    "code_expires_at": now + otp_ttl,
                    "reset_expires_at": now + otp_ttl,
                    "email_verified": False,
                    "code_attempts": 0,
                },
                "$inc": {"resend_count": 1},
            },
            upsert=True,
        )
        mongo.db.users.update_one({"email": email}, {"$set": {"forgot_password": True}})

        sent, message, dev_code = _send_password_reset_code(email, code)
        if not sent:
            return jsonify(success=False, message=message)

        response = {
            "success": True,
            "message": message,
            "next_step": "verify",
            "email": email,
            "expires_in": otp_ttl,
            "resend_after": cooldown,
        }
        if dev_code:
            response["verification_code"] = dev_code
        return jsonify(response)

    @app.route("/api/v1/forgot-password/verify", methods=["POST"])
    @app.route("/api/forgot-password/verify", methods=["POST"])
    def forgot_password_verify():
        email = _normalize_email(_request_value("email"))
        code = _clean_text(_request_value("code"))
        now = time.time()

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error, next_step="email"), 400
        if not code:
            return jsonify(success=False, message="Enter the reset code.")
        if not code.isdigit() or len(code) != 4:
            return jsonify(success=False, message="Enter the 4-digit reset code.")

        reset = _active_password_reset(email)
        if not reset:
            return jsonify(success=False, message="Reset attempt expired. Start again.", next_step="email")
        if reset.get("code_expires_at", 0) < now:
            return jsonify(success=False, message="Code expired. Resend a new code.", next_step="verify", expired=True)

        max_attempts = current_app.config["PASSWORD_RESET_MAX_CODE_ATTEMPTS"]
        if reset.get("code_attempts", 0) >= max_attempts:
            return jsonify(success=False, message="Too many attempts. Resend a new code.", next_step="verify")

        if reset.get("verification_code") != code:
            attempts = reset.get("code_attempts", 0) + 1
            mongo.db.password_resets.update_one({"email": email}, {"$set": {"code_attempts": attempts}})
            remaining = max(0, max_attempts - attempts)
            return jsonify(success=False, message=f"Invalid code. {remaining} attempts left.", attempts_left=remaining)

        mongo.db.password_resets.update_one(
            {"email": email},
            {
                "$set": {"email_verified": True, "verified_at": now},
                "$unset": {"verification_code": ""},
            },
        )
        return jsonify(success=True, message="Code verified. Set your new password.", next_step="password")

    @app.route("/api/v1/forgot-password/complete", methods=["POST"])
    @app.route("/api/forgot-password/complete", methods=["POST"])
    def forgot_password_complete():
        email = _normalize_email(_request_value("email"))
        password = _password_value(_request_value("password"))
        confirm_password = _password_value(_request_value("confirm_password"))

        email_error = _validate_email(email)
        if email_error:
            return jsonify(success=False, message=email_error, next_step="email"), 400

        reset = _active_password_reset(email)
        if not reset or not reset.get("email_verified"):
            return jsonify(success=False, message="Verify your email first.", next_step="email")

        password_error = _validate_password(password)
        if password_error:
            return jsonify(success=False, message=password_error)
        if password != confirm_password:
            return jsonify(success=False, message="Passwords do not match.")

        result = mongo.db.users.update_one(
            {"email": email},
            {
                "$set": {
                    "password": generate_password_hash(password),
                    "forgot_password": False,
                },
                "$unset": {
                    "temp_password": "",
                    "temp_password_created_at": "",
                    "temp_password_expires_at": "",
                },
            },
        )
        if result.matched_count == 0:
            mongo.db.password_resets.delete_one({"email": email})
            return jsonify(success=False, message="No account found with that email.", next_step="email"), 404

        mongo.db.password_resets.delete_one({"email": email})
        return jsonify(success=True, message="Password updated. Sign in with your new password.", next_step="signin")
