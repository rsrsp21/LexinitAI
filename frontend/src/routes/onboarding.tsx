import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  BriefcaseBusiness,
  Check,
  GraduationCap,
  LoaderCircle,
  Sparkles,
  UserRound,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  apiErrorMessage,
  getMe,
  type ProfileType,
  updateProfile,
} from "@/lib/api";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: async () => {
    const me = await getMe().catch(() => null);
    if (!me) throw redirect({ to: "/login" });
    if (me.user.profile_complete !== false) throw redirect({ to: "/app" });
  },
  component: OnboardingPage,
});

const options = [
  {
    value: "student" as const,
    title: "Student",
    description: "School, college, or university",
    icon: GraduationCap,
  },
  {
    value: "professional" as const,
    title: "Professional",
    description: "Learning alongside your work",
    icon: BriefcaseBusiness,
  },
  {
    value: "independent" as const,
    title: "Independent learner",
    description: "Learning on your own terms",
    icon: UserRound,
  },
];

function OnboardingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<1 | 2>(1);
  const [direction, setDirection] = useState(1);
  const [name, setName] = useState("");
  const [profileType, setProfileType] = useState<ProfileType | "">("");
  const [institutionName, setInstitutionName] = useState("");
  const [gradeOrClass, setGradeOrClass] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [professionalRole, setProfessionalRole] = useState("");
  const [workExperience, setWorkExperience] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const continueToDetails = () => {
    setError("");
    if (name.trim().length < 2) return setError("Enter your name to continue.");
    if (!profileType)
      return setError("Choose the option that best describes you.");
    setDirection(1);
    setStep(2);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (step === 1) return continueToDetails();
    setError("");
    if (!profileType)
      return setError("Choose the option that best describes you.");
    if (
      profileType === "student" &&
      (!institutionName.trim() || !gradeOrClass.trim())
    )
      return setError("Enter your school or college and grade or class.");
    if (
      profileType === "professional" &&
      (!organizationName.trim() || workExperience === "")
    )
      return setError("Enter your organization and work experience.");
    if (
      profileType === "professional" &&
      (!Number.isInteger(Number(workExperience)) ||
        Number(workExperience) < 0 ||
        Number(workExperience) > 70)
    )
      return setError(
        "Work experience must be a whole number between 0 and 70.",
      );
    setSaving(true);
    try {
      const result = await updateProfile({
        name: name.trim(),
        profile_type: profileType,
        institution_name:
          profileType === "student" ? institutionName.trim() : null,
        grade_or_class: profileType === "student" ? gradeOrClass.trim() : null,
        organization_name:
          profileType === "professional" ? organizationName.trim() : null,
        professional_role:
          profileType === "professional"
            ? professionalRole.trim() || null
            : null,
        work_experience_years:
          profileType === "professional" ? Number(workExperience) : null,
      });
      queryClient.setQueryData(["me"], {
        authenticated: true,
        user: result.user,
      });
      await navigate({ to: "/app", replace: true, viewTransition: true });
    } catch (cause) {
      setError(apiErrorMessage(cause, "We could not save your details."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-background px-4 py-8 sm:grid sm:place-items-center">
      <motion.div
        animate={{ x: [0, 70, 0], y: [0, 45, 0], scale: [1, 1.15, 1] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -left-24 -top-24 h-96 w-96 rounded-full bg-accent/20 blur-[90px]"
      />
      <motion.div
        animate={{ x: [0, -50, 0], y: [0, -35, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -bottom-32 -right-20 h-96 w-96 rounded-full bg-primary/15 blur-[100px]"
      />

      <motion.section
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 180, damping: 22 }}
        className="relative mx-auto w-full max-w-3xl overflow-hidden rounded-[34px] border border-border bg-card/95 shadow-[var(--shadow-elegant)] backdrop-blur-xl"
      >
        <div className="border-b border-border px-6 pb-5 pt-6 sm:px-9 sm:pt-8">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <motion.div
                animate={{ rotate: [0, 8, -8, 0] }}
                transition={{ duration: 4, repeat: Infinity }}
                className="grid h-11 w-11 place-items-center rounded-2xl bg-accent text-accent-foreground"
              >
                <Sparkles className="h-5 w-5" />
              </motion.div>
              <div>
                <div className="text-sm font-semibold text-accent">
                  Build your learning space
                </div>
                <div className="text-xs text-muted-foreground">
                  Step {step} of 2
                </div>
              </div>
            </div>
            <span className="font-display text-2xl text-accent">
              {step * 50}%
            </span>
          </div>
          <div className="mt-5 h-2 overflow-hidden rounded-full bg-muted">
            <motion.div
              animate={{ width: `${step * 50}%` }}
              transition={{ type: "spring", stiffness: 180, damping: 24 }}
              className="relative h-full rounded-full bg-accent"
            >
              <motion.span
                animate={{ x: ["-100%", "240%"] }}
                transition={{
                  duration: 1.8,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/55 to-transparent"
              />
            </motion.div>
          </div>
        </div>

        <form onSubmit={submit} className="p-6 sm:p-9">
          <AnimatePresence mode="wait" custom={direction}>
            {step === 1 ? (
              <motion.div
                key="identity"
                custom={direction}
                initial={{ opacity: 0, x: 36 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -30 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <h1 className="font-display text-4xl tracking-tight sm:text-5xl">
                  How do you learn?
                </h1>
                <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
                  This tunes examples and pacing. It never restricts the topics
                  or difficulty levels you can choose.
                </p>
                <div className="mt-7">
                  <Label htmlFor="onboarding-name">Your name</Label>
                  <Input
                    id="onboarding-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Enter your name"
                    maxLength={80}
                    className="mt-2 h-12 rounded-2xl bg-background px-4"
                    required
                  />
                </div>
                <fieldset className="mt-7">
                  <legend className="text-sm font-medium">
                    Choose what fits you best
                  </legend>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    {options.map((option, index) => {
                      const Icon = option.icon;
                      const selected = profileType === option.value;
                      return (
                        <motion.button
                          key={option.value}
                          type="button"
                          onClick={() => {
                            setProfileType(option.value);
                            setError("");
                          }}
                          whileHover={{ y: -4 }}
                          whileTap={{ scale: 0.98 }}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.08 + index * 0.06 }}
                          className={`relative overflow-hidden rounded-[22px] border p-5 text-left transition ${selected ? "border-accent bg-accent/10 shadow-[var(--shadow-glow)]" : "border-border bg-background hover:border-accent/45"}`}
                        >
                          {selected && (
                            <motion.span
                              layoutId="selected-profile"
                              className="absolute right-3 top-3 grid h-6 w-6 place-items-center rounded-full bg-accent text-accent-foreground"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </motion.span>
                          )}
                          <span
                            className={`grid h-11 w-11 place-items-center rounded-2xl ${selected ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"}`}
                          >
                            <Icon className="h-5 w-5" />
                          </span>
                          <span className="mt-5 block font-display text-xl tracking-tight">
                            {option.title}
                          </span>
                          <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                            {option.description}
                          </span>
                        </motion.button>
                      );
                    })}
                  </div>
                </fieldset>
              </motion.div>
            ) : (
              <motion.div
                key="details"
                custom={direction}
                initial={{ opacity: 0, x: direction > 0 ? 36 : -36 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 30 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <h1 className="font-display text-4xl tracking-tight sm:text-5xl">
                  A little more context
                </h1>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  You can change these details later from your profile.
                </p>
                {profileType === "student" && (
                  <div className="mt-8 grid gap-5 sm:grid-cols-2">
                    <SetupField
                      id="institution"
                      label="School, college, or university"
                      value={institutionName}
                      onChange={setInstitutionName}
                      placeholder="Enter institution name"
                    />
                    <SetupField
                      id="grade"
                      label="Grade or class"
                      value={gradeOrClass}
                      onChange={setGradeOrClass}
                      placeholder="Enter grade or class"
                    />
                  </div>
                )}
                {profileType === "professional" && (
                  <div className="mt-8 grid gap-5 sm:grid-cols-2">
                    <SetupField
                      id="organization"
                      label="Organization"
                      value={organizationName}
                      onChange={setOrganizationName}
                      placeholder="Enter organization name"
                    />
                    <SetupField
                      id="role"
                      label="Role or job title (optional)"
                      value={professionalRole}
                      onChange={setProfessionalRole}
                      placeholder="Enter role or job title"
                      required={false}
                    />
                    <SetupField
                      id="experience"
                      label="Work experience (years)"
                      value={workExperience}
                      onChange={setWorkExperience}
                      placeholder="Enter years of experience"
                      type="number"
                    />
                  </div>
                )}
                {profileType === "independent" && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="mt-8 rounded-[24px] border border-accent/25 bg-accent/10 p-6"
                  >
                    <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-accent-foreground">
                      <Check className="h-5 w-5" />
                    </div>
                    <h2 className="mt-5 font-display text-2xl tracking-tight">
                      You are ready to explore
                    </h2>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      Independent learners do not need to add school or
                      workplace information.
                    </p>
                  </motion.div>
                )}
                <div className="mt-8 rounded-2xl bg-muted/60 px-4 py-3 text-sm text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    Your control stays the same:
                  </span>{" "}
                  any subject, any level, whenever you choose.
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {error && (
            <motion.p
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="mt-5 rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              {error}
            </motion.p>
          )}
          <div className="mt-8 flex items-center justify-between gap-3">
            {step === 2 ? (
              <button
                type="button"
                onClick={() => {
                  setDirection(-1);
                  setStep(1);
                  setError("");
                }}
                className="inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" /> Back
              </button>
            ) : (
              <span />
            )}
            <Button
              type="submit"
              disabled={saving}
              className="group h-12 rounded-full px-6 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
            >
              {saving ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : step === 1 ? (
                <>
                  Continue{" "}
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
                </>
              ) : (
                <>
                  Enter my learning dashboard <Sparkles className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </form>
      </motion.section>
    </main>
  );
}

function SetupField({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required = true,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
        min={type === "number" ? 0 : undefined}
        max={type === "number" ? 70 : undefined}
        className="mt-2 h-12 rounded-2xl bg-background px-4 transition focus:shadow-[var(--shadow-glow)]"
      />
    </motion.div>
  );
}
