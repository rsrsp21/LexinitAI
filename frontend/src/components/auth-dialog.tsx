import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  RefreshCw,
  X,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { requestJson, type ApiResult } from "@/lib/api";

export type AuthMode = "signin" | "signup";
type SignupStep = "email" | "verify" | "password" | "terms";
type ForgotStep = "email" | "verify" | "password";
type SignupResult = ApiResult & {
  next_step?: SignupStep | "signin" | "app";
  verification_code?: string;
  expires_in?: number;
  resend_after?: number;
};
type ForgotPasswordResult = ApiResult & {
  next_step?: ForgotStep | "signin";
  verification_code?: string;
  expires_in?: number;
  resend_after?: number;
};

export function AuthDialog({
  open,
  mode: requestedMode,
  onOpenChange,
}: {
  open: boolean;
  mode: AuthMode;
  onOpenChange: (open: boolean) => void;
}) {
  const [mode, setMode] = useState<AuthMode>(requestedMode);
  const [signupStep, setSignupStep] = useState<SignupStep>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [otpSeconds, setOtpSeconds] = useState(0);
  const [resendSeconds, setResendSeconds] = useState(0);
  const [forgotPassword, setForgotPassword] = useState(false);
  const [forgotStep, setForgotStep] = useState<ForgotStep>("email");
  const [acceptedLegal, setAcceptedLegal] = useState(false);
  const [openedTerms, setOpenedTerms] = useState(false);
  const [openedPrivacy, setOpenedPrivacy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    setMode(requestedMode);
    setSignupStep("email");
    setForgotPassword(false);
    setForgotStep("email");
    setAcceptedLegal(false);
    setOpenedTerms(false);
    setOpenedPrivacy(false);
    resetStatus();
  }, [open, requestedMode]);

  useEffect(() => {
    const isSignupVerify = mode === "signup" && signupStep === "verify";
    const isForgotVerify =
      mode === "signin" && forgotPassword && forgotStep === "verify";
    if (!open || (!isSignupVerify && !isForgotVerify)) return;
    const timer = window.setInterval(() => {
      setOtpSeconds((value) => Math.max(0, value - 1));
      setResendSeconds((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [forgotPassword, forgotStep, open, mode, signupStep]);

  const resetStatus = () => {
    setMessage("");
    setError("");
  };

  const goToApp = (destination = "/app") => {
    onOpenChange(false);
    navigate({ to: destination });
  };

  const switchMode = () => {
    resetStatus();
    setForgotPassword(false);
    setForgotStep("email");
    setAcceptedLegal(false);
    setOpenedTerms(false);
    setOpenedPrivacy(false);
    setSignupStep("email");
    setMode(mode === "signin" ? "signup" : "signin");
  };

  const applySignupResult = (data: SignupResult) => {
    if (data.success === false)
      throw new Error(data.message || "Signup failed.");
    if (data.next_step === "password") setSignupStep("password");
    if (data.next_step === "terms") setSignupStep("terms");
    if (data.next_step === "verify") setSignupStep("verify");
    if (data.next_step === "signin") {
      setMode("signin");
      setSignupStep("email");
      setAcceptedLegal(false);
    }
    if (data.next_step === "app") {
      goToApp("/onboarding");
    }
    if (typeof data.expires_in === "number") setOtpSeconds(data.expires_in);
    if (typeof data.resend_after === "number")
      setResendSeconds(data.resend_after);
    setMessage(
      data.verification_code
        ? `Local dev verification code: ${data.verification_code}`
        : data.message || "",
    );
  };

  const handleSignin = async () => {
    const emailError = validateEmail(email);
    if (emailError) throw new Error(emailError);
    if (!password) throw new Error("Enter your password.");

    const form = new FormData();
    form.append("login-email", email);
    form.append("login-password", password);
    const data = await requestJson<ApiResult>("/login", {
      method: "POST",
      form,
    });
    if (data.success === false)
      throw new Error(data.message || "Login failed.");
    goToApp();
  };

  const handleForgotPassword = async () => {
    const emailError = validateEmail(email);
    if (emailError) throw new Error(emailError);

    const data = await requestJson<ForgotPasswordResult>(
      "/api/v1/forgot-password",
      {
        method: "POST",
        json: { email },
      },
    );
    applyForgotResult(data);
    setPassword("");
  };

  const applyForgotResult = (data: ForgotPasswordResult) => {
    if (data.success === false)
      throw new Error(data.message || "Password reset failed.");
    if (data.next_step === "verify") setForgotStep("verify");
    if (data.next_step === "password") setForgotStep("password");
    if (data.next_step === "signin") {
      setForgotPassword(false);
      setForgotStep("email");
      setMode("signin");
      setPassword("");
      setConfirmPassword("");
      setVerificationCode("");
    }
    if (typeof data.expires_in === "number") setOtpSeconds(data.expires_in);
    if (typeof data.resend_after === "number")
      setResendSeconds(data.resend_after);
    setMessage(
      data.verification_code
        ? `Local dev reset code: ${data.verification_code}`
        : data.message || "",
    );
  };

  const verifyForgotPasswordCode = async () => {
    if (!/^\d{4}$/.test(verificationCode.trim())) {
      throw new Error("Enter the 4-digit reset code.");
    }

    const data = await requestJson<ForgotPasswordResult>(
      "/api/v1/forgot-password/verify",
      {
        method: "POST",
        json: { email, code: verificationCode },
      },
    );
    applyForgotResult(data);
  };

  const completeForgotPassword = async () => {
    const passwordError = validatePassword(password);
    if (passwordError) throw new Error(passwordError);
    if (password !== confirmPassword)
      throw new Error("Passwords do not match.");

    const data = await requestJson<ForgotPasswordResult>(
      "/api/v1/forgot-password/complete",
      {
        method: "POST",
        json: { email, password, confirm_password: confirmPassword },
      },
    );
    applyForgotResult(data);
  };

  const startSignup = async (resend = false) => {
    const emailError = validateEmail(email);
    if (emailError) throw new Error(emailError);

    const data = await requestJson<SignupResult>("/auth/signup/start", {
      method: "POST",
      json: { email, resend },
    });
    applySignupResult(data);
  };

  const verifyEmail = async () => {
    if (!/^\d{4}$/.test(verificationCode.trim())) {
      throw new Error("Enter the 4-digit verification code.");
    }

    const data = await requestJson<SignupResult>("/auth/signup/verify", {
      method: "POST",
      json: { email, code: verificationCode },
    });
    applySignupResult(data);
  };

  const completeSignup = async () => {
    if (!acceptedLegal || !openedTerms || !openedPrivacy) {
      throw new Error(
        "Open the Terms of Service and Privacy Policy, then agree before creating your account.",
      );
    }

    const data = await requestJson<SignupResult>("/auth/signup/complete", {
      method: "POST",
      json: {
        email,
        password,
        confirm_password: confirmPassword,
        agreed_terms: true,
        agreed_privacy: true,
      },
    });
    applySignupResult(data);
    setPassword("");
    setConfirmPassword("");
    setAcceptedLegal(false);
  };

  const reviewSignupTerms = () => {
    const passwordError = validatePassword(password);
    if (passwordError) throw new Error(passwordError);
    if (password !== confirmPassword)
      throw new Error("Passwords do not match.");
    setSignupStep("terms");
  };

  const resendCode = async () => {
    resetStatus();
    setLoading(true);
    try {
      if (mode === "signin" && forgotPassword) {
        const data = await requestJson<ForgotPasswordResult>(
          "/api/v1/forgot-password",
          {
            method: "POST",
            json: { email, resend: true },
          },
        );
        applyForgotResult(data);
      } else {
        await startSignup(true);
      }
      setVerificationCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    resetStatus();
    setLoading(true);
    try {
      if (mode === "signin") {
        if (forgotPassword) {
          if (forgotStep === "email") {
            await handleForgotPassword();
          } else if (forgotStep === "verify") {
            await verifyForgotPasswordCode();
          } else {
            await completeForgotPassword();
          }
        } else {
          await handleSignin();
        }
      } else if (signupStep === "email") {
        await startSignup();
      } else if (signupStep === "verify") {
        await verifyEmail();
      } else if (signupStep === "password") {
        reviewSignupTerms();
      } else {
        await completeSignup();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const stepIndex =
    signupStep === "email"
      ? 1
      : signupStep === "verify"
        ? 2
        : signupStep === "password"
          ? 3
          : 4;
  const submitDisabled =
    loading ||
    (mode === "signup" &&
      signupStep === "terms" &&
      (!acceptedLegal || !openedTerms || !openedPrivacy));
  const title =
    mode === "signin"
      ? forgotPassword
        ? forgotTitle(forgotStep)
        : "Sign in to Lexinit"
      : signupTitle(signupStep);
  const description =
    mode === "signin"
      ? forgotPassword
        ? forgotDescription(forgotStep, email)
        : "Continue to your learning dashboard."
      : signupDescription(signupStep, email);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100svh-32px)] w-[calc(100vw-32px)] flex-col overflow-hidden border-border bg-card p-0 shadow-[var(--shadow-elegant)] sm:max-w-[420px] sm:rounded-2xl">
        <div className="border-b border-border px-5 py-4">
          <DialogTitle className="pr-8 font-display text-2xl tracking-tight">
            {title}
          </DialogTitle>
          <DialogDescription className="mt-1.5 text-sm">
            {description}
          </DialogDescription>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-5 pb-5 pt-4">
          <div className="mb-4 grid grid-cols-2 rounded-full border border-border bg-muted/50 p-1 text-sm">
            <button
              type="button"
              onClick={() => {
                setMode("signin");
                setForgotPassword(false);
                setForgotStep("email");
                setAcceptedLegal(false);
                setOpenedTerms(false);
                setOpenedPrivacy(false);
                setSignupStep("email");
                resetStatus();
              }}
              className={`rounded-full px-4 py-1.5 font-medium transition ${
                mode === "signin"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("signup");
                setForgotPassword(false);
                setForgotStep("email");
                setAcceptedLegal(false);
                setOpenedTerms(false);
                setOpenedPrivacy(false);
                setSignupStep("email");
                resetStatus();
              }}
              className={`rounded-full px-4 py-1.5 font-medium transition ${
                mode === "signup"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Create account
            </button>
          </div>

          {mode === "signup" && (
            <div className="mb-4">
              <div className="mb-2 text-xs text-muted-foreground">
                <span>Step {stepIndex} of 4</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-300"
                  style={{ width: `${stepIndex * 25}%` }}
                />
              </div>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="app-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1">
              {mode === "signin" && (
                <>
                  {(!forgotPassword || forgotStep === "email") && (
                    <Field
                      label="Email"
                      type="email"
                      placeholder="Enter your email address"
                      value={email}
                      onChange={setEmail}
                    />
                  )}
                  {!forgotPassword && (
                    <>
                      <Field
                        label="Password"
                        type="password"
                        placeholder="Enter your password"
                        value={password}
                        onChange={setPassword}
                      />
                      <div className="text-right">
                        <button
                          type="button"
                          onClick={() => {
                            resetStatus();
                            setForgotPassword(true);
                            setForgotStep("email");
                            setPassword("");
                            setConfirmPassword("");
                            setVerificationCode("");
                          }}
                          className="text-sm font-medium text-foreground underline underline-offset-4 transition hover:text-accent"
                        >
                          Forgot password?
                        </button>
                      </div>
                    </>
                  )}
                  {forgotPassword && forgotStep === "verify" && (
                    <>
                      <Field
                        label="Reset code"
                        type="text"
                        placeholder="Enter 4-digit code"
                        value={verificationCode}
                        onChange={setVerificationCode}
                        inputMode="numeric"
                        autoComplete="one-time-code"
                      />
                      <div className="flex items-center justify-between rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
                        <span>
                          {otpSeconds > 0
                            ? `Code expires in ${formatSeconds(otpSeconds)}`
                            : "Code expired"}
                        </span>
                        <button
                          type="button"
                          onClick={resendCode}
                          disabled={loading || resendSeconds > 0}
                          className="inline-flex items-center gap-1 font-medium text-foreground transition hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          {resendSeconds > 0
                            ? `Resend in ${resendSeconds}s`
                            : "Resend"}
                        </button>
                      </div>
                    </>
                  )}
                  {forgotPassword && forgotStep === "password" && (
                    <>
                      <Field
                        label="New password"
                        type="password"
                        placeholder="At least 8 characters"
                        value={password}
                        onChange={setPassword}
                      />
                      <Field
                        label="Confirm password"
                        type="password"
                        placeholder="Enter password again"
                        value={confirmPassword}
                        onChange={setConfirmPassword}
                      />
                      <PasswordRules
                        password={password}
                        confirmPassword={confirmPassword}
                      />
                    </>
                  )}
                  {forgotPassword && (
                    <button
                      type="button"
                      onClick={() => {
                        resetStatus();
                        if (forgotStep === "email") {
                          setForgotPassword(false);
                        } else {
                          setForgotStep(
                            forgotStep === "verify" ? "email" : "verify",
                          );
                        }
                      }}
                      className="inline-flex w-fit items-center gap-1 text-sm font-medium text-foreground transition hover:text-accent"
                    >
                      <ArrowLeft className="h-3.5 w-3.5" />{" "}
                      {forgotStep === "email" ? "Back to sign in" : "Back"}
                    </button>
                  )}
                </>
              )}

              {mode === "signup" && signupStep === "email" && (
                <Field
                  label="Email"
                  type="email"
                  placeholder="Enter your email address"
                  value={email}
                  onChange={setEmail}
                />
              )}

              {mode === "signup" && signupStep === "verify" && (
                <>
                  <Field
                    label="Verification code"
                    type="text"
                    placeholder="Enter 4-digit code"
                    value={verificationCode}
                    onChange={setVerificationCode}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                  />
                  <div className="flex items-center justify-between rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
                    <span>
                      {otpSeconds > 0
                        ? `Code expires in ${formatSeconds(otpSeconds)}`
                        : "Code expired"}
                    </span>
                    <button
                      type="button"
                      onClick={resendCode}
                      disabled={loading || resendSeconds > 0}
                      className="inline-flex items-center gap-1 font-medium text-foreground transition hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {resendSeconds > 0
                        ? `Resend in ${resendSeconds}s`
                        : "Resend"}
                    </button>
                  </div>
                </>
              )}

              {mode === "signup" && signupStep === "password" && (
                <>
                  <Field
                    label="Password"
                    type="password"
                    placeholder="At least 8 characters"
                    value={password}
                    onChange={setPassword}
                  />
                  <Field
                    label="Confirm password"
                    type="password"
                    placeholder="Enter password again"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                  />
                  <PasswordRules
                    password={password}
                    confirmPassword={confirmPassword}
                  />
                </>
              )}

              {mode === "signup" && signupStep === "terms" && (
                <div className="space-y-3">
                  <label className="flex gap-3 rounded-2xl border border-border bg-muted/35 p-4 text-sm leading-6">
                    <input
                      type="checkbox"
                      checked={acceptedLegal}
                      onChange={(event) =>
                        setAcceptedLegal(event.target.checked)
                      }
                      disabled={!openedTerms || !openedPrivacy}
                      className="mt-1 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
                    />
                    <span className="text-muted-foreground">
                      I agree to Lexinit's{" "}
                      <Link
                        to="/terms"
                        target="_blank"
                        onClick={() => setOpenedTerms(true)}
                        className="font-medium text-foreground underline underline-offset-4"
                      >
                        Terms of Service
                      </Link>{" "}
                      and{" "}
                      <Link
                        to="/privacy"
                        target="_blank"
                        onClick={() => setOpenedPrivacy(true)}
                        className="font-medium text-foreground underline underline-offset-4"
                      >
                        Privacy Policy
                      </Link>
                      .
                    </span>
                  </label>
                  <p className="px-1 text-xs leading-5 text-muted-foreground">
                    Open both links to enable the agreement, then create your
                    account.
                  </p>
                </div>
              )}

              {error && <p className="text-sm text-destructive">{error}</p>}
              {message && (
                <p className="text-sm text-muted-foreground">{message}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={submitDisabled}
              className="group mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading
                ? "Working..."
                : submitLabel(mode, signupStep, forgotPassword, forgotStep)}
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            {mode === "signin" ? "New to Lexinit?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={switchMode}
              className="font-medium text-foreground underline underline-offset-4 hover:text-accent"
            >
              {mode === "signin" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function signupTitle(step: SignupStep) {
  if (step === "email") return "Create your account";
  if (step === "verify") return "Verify your email";
  if (step === "password") return "Set your password";
  return "Review and agree";
}

function signupDescription(step: SignupStep, email: string) {
  if (step === "email")
    return "Start with your email. We will send a short verification code.";
  if (step === "verify")
    return `Enter the code sent to ${email || "your email"}.`;
  if (step === "password") return "Create a secure password for your account.";
  return "Accept the Terms and Privacy Policy to finish signup.";
}

function forgotTitle(step: ForgotStep) {
  if (step === "email") return "Reset your password";
  if (step === "verify") return "Enter reset code";
  return "Set a new password";
}

function forgotDescription(step: ForgotStep, email: string) {
  if (step === "email")
    return "Enter your email. We will send a 4-digit reset code.";
  if (step === "verify")
    return `Enter the code sent to ${email || "your email"}.`;
  return "Choose a new password for your Lexinit account.";
}

function submitLabel(
  mode: AuthMode,
  step: SignupStep,
  forgotPassword = false,
  forgotStep: ForgotStep = "email",
) {
  if (mode === "signin") {
    if (!forgotPassword) return "Sign in";
    if (forgotStep === "email") return "Send code";
    if (forgotStep === "verify") return "Verify code";
    return "Update password";
  }
  if (step === "email") return "Continue";
  if (step === "verify") return "Verify email";
  if (step === "password") return "Continue";
  return "Create account";
}

function formatSeconds(total: number) {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function validateEmail(value: string) {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    return "Enter a valid email address.";
  }
  return "";
}

function validatePassword(value: string) {
  if (value.length < 8) return "Password must be at least 8 characters.";
  if (value.length > 128) return "Password must be 128 characters or fewer.";
  if (!/[A-Za-z]/.test(value))
    return "Password must include at least one letter.";
  if (!/\d/.test(value)) return "Password must include at least one number.";
  return "";
}

function PasswordRules({
  password,
  confirmPassword,
}: {
  password: string;
  confirmPassword: string;
}) {
  const rules = [
    { label: "8 or more characters", valid: password.length >= 8 },
    { label: "At least one letter", valid: /[A-Za-z]/.test(password) },
    { label: "At least one number", valid: /\d/.test(password) },
    {
      label: "Passwords match",
      valid: Boolean(confirmPassword) && password === confirmPassword,
    },
  ];

  return (
    <ul className="grid gap-1 text-xs text-muted-foreground">
      {rules.map((rule) => (
        <li
          key={rule.label}
          className={`flex items-center gap-1.5 ${rule.valid ? "text-emerald-600 dark:text-emerald-400" : ""}`}
        >
          {rule.valid ? (
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <X
              className="h-3.5 w-3.5 text-muted-foreground/70"
              aria-hidden="true"
            />
          )}
          {rule.label}
        </li>
      ))}
    </ul>
  );
}

function Field({
  label,
  type,
  placeholder,
  value,
  onChange,
  disabled = false,
  inputMode,
  autoComplete,
  min,
  max,
  step,
  maxLength,
}: {
  label: string;
  type: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  inputMode?:
    | "numeric"
    | "text"
    | "email"
    | "tel"
    | "url"
    | "search"
    | "none"
    | "decimal";
  autoComplete?: string;
  min?: number;
  max?: number;
  step?: number;
  maxLength?: number;
}) {
  const [visible, setVisible] = useState(false);
  const isPassword = type === "password";
  return (
    <label className="block">
      <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </span>
      <div className="relative mt-1.5">
        <input
          type={isPassword && visible ? "text" : type}
          placeholder={placeholder}
          value={value}
          disabled={disabled}
          required
          inputMode={inputMode}
          autoComplete={autoComplete}
          min={min}
          max={max}
          step={step}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-xl border border-border bg-background px-4 py-2.5 pr-11 text-sm outline-none transition placeholder:text-muted-foreground/70 focus:border-accent disabled:cursor-not-allowed disabled:opacity-70"
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            aria-label={visible ? "Hide password" : "Show password"}
            className="absolute inset-y-0 right-3 grid place-items-center text-muted-foreground hover:text-foreground"
          >
            {visible ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </button>
        )}
      </div>
    </label>
  );
}
