import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Award,
  Briefcase,
  BriefcaseBusiness,
  Building2,
  Calendar,
  CheckCircle2,
  Eye,
  EyeOff,
  GraduationCap,
  Hash,
  KeyRound,
  LoaderCircle,
  LogOut,
  Pencil,
  Save,
  School,
  UserRound,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { type ComponentType, type FormEvent, type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCurrentUser } from "@/hooks/use-current-user";
import {
  apiErrorMessage,
  completePasswordChange,
  getCourses,
  type MeResponse,
  type ProfileType,
  startPasswordChange,
  updateProfile,
  verifyPasswordChange,
  logout,
} from "@/lib/api";

export const Route = createFileRoute("/app/profile")({
  head: () => ({
    meta: [
      { title: "Profile - Lexinit" },
      {
        name: "description",
        content: "Manage your Lexinit profile and password.",
      },
    ],
  }),
  validateSearch: (search: Record<string, unknown>) => {
    return {
      tab: (search.tab as string) || "details",
    };
  },
  component: ProfilePage,
});

type Notice = { tone: "success" | "error"; text: string } | null;

const PROFILE_TYPES: Array<{
  value: ProfileType;
  title: string;
  description: string;
  icon: typeof GraduationCap;
}> = [
  {
    value: "student",
    title: "Student",
    description: "School, college, or university",
    icon: GraduationCap,
  },
  {
    value: "professional",
    title: "Professional",
    description: "Working at an organization",
    icon: BriefcaseBusiness,
  },
  {
    value: "independent",
    title: "Independent learner",
    description: "Learning outside school or work",
    icon: UserRound,
  },
];

function ProfilePage() {
  const queryClient = useQueryClient();
  const currentUser = useCurrentUser();
  const user = currentUser.data?.user;
  const courses = useQuery({
    queryKey: ["courses"],
    queryFn: getCourses,
    staleTime: 15_000,
  });
  const earnedBadges = (courses.data?.courses ?? []).filter(
    (course) => course.status === "completed",
  );
  const [name, setName] = useState("");
  const [profileType, setProfileType] = useState<ProfileType>("independent");
  const [institutionName, setInstitutionName] = useState("");
  const [gradeOrClass, setGradeOrClass] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [professionalRole, setProfessionalRole] = useState("");
  const [workExperience, setWorkExperience] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileNotice, setProfileNotice] = useState<Notice>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);

  const [passwordStep, setPasswordStep] = useState<"start" | "verify" | "new">(
    "start",
  );
  const [passwordCode, setPasswordCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordNotice, setPasswordNotice] = useState<Notice>(null);

  useEffect(() => {
    if (!user) return;
    setName(user.name ?? "");
    setProfileType(user.profile_type ?? "independent");
    setInstitutionName(user.institution_name ?? "");
    setGradeOrClass(user.grade_or_class ?? "");
    setOrganizationName(user.organization_name ?? "");
    setProfessionalRole(user.professional_role ?? "");
    setWorkExperience(
      user.work_experience_years == null
        ? ""
        : String(user.work_experience_years),
    );
  }, [user]);

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setProfileNotice(null);

    if (name.trim().length < 2) {
      setProfileNotice({
        tone: "error",
        text: "Enter a name with at least 2 characters.",
      });
      return;
    }
    if (
      profileType === "student" &&
      (!institutionName.trim() || !gradeOrClass.trim())
    ) {
      setProfileNotice({
        tone: "error",
        text: "Add your school or college name and your grade or class.",
      });
      return;
    }
    if (
      profileType === "professional" &&
      (!organizationName.trim() || workExperience === "")
    ) {
      setProfileNotice({
        tone: "error",
        text: "Add your organization and years of work experience.",
      });
      return;
    }
    if (
      profileType === "professional" &&
      (!Number.isInteger(Number(workExperience)) ||
        Number(workExperience) < 0 ||
        Number(workExperience) > 70)
    ) {
      setProfileNotice({
        tone: "error",
        text: "Work experience must be a whole number between 0 and 70.",
      });
      return;
    }

    setSavingProfile(true);
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
      queryClient.setQueryData<MeResponse>(["me"], {
        authenticated: true,
        user: result.user,
      });
      setProfileNotice({
        tone: "success",
        text: "Your profile has been updated.",
      });
      setIsEditingProfile(false);
    } catch (error) {
      setProfileNotice({
        tone: "error",
        text: apiErrorMessage(error, "Your profile could not be updated."),
      });
    } finally {
      setSavingProfile(false);
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordNotice(null);

    if (passwordStep === "start") {
      setSavingPassword(true);
      try {
        const result = await startPasswordChange();
        setPasswordStep("verify");
        setPasswordNotice({
          tone: "success",
          text: result.verification_code
            ? `Local development code: ${result.verification_code}`
            : "We sent a 4-digit code to your email.",
        });
      } catch (error) {
        setPasswordNotice({
          tone: "error",
          text: apiErrorMessage(error, "We could not send a code."),
        });
      } finally {
        setSavingPassword(false);
      }
      return;
    }
    if (passwordStep === "verify") {
      if (!/^\d{4}$/.test(passwordCode)) {
        setPasswordNotice({ tone: "error", text: "Enter the 4-digit code." });
        return;
      }
      setSavingPassword(true);
      try {
        await verifyPasswordChange(passwordCode);
        setPasswordStep("new");
        setPasswordNotice({
          tone: "success",
          text: "Code verified. Choose a new password.",
        });
      } catch (error) {
        setPasswordNotice({
          tone: "error",
          text: apiErrorMessage(error, "We could not verify that code."),
        });
      } finally {
        setSavingPassword(false);
      }
      return;
    }
    if (!newPassword || !confirmPassword) {
      setPasswordNotice({
        tone: "error",
        text: "Fill in both password fields.",
      });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordNotice({ tone: "error", text: "New passwords do not match." });
      return;
    }
    if (
      newPassword.length < 8 ||
      !/[A-Za-z]/.test(newPassword) ||
      !/\d/.test(newPassword)
    ) {
      setPasswordNotice({
        tone: "error",
        text: "Use at least 8 characters with a letter and a number.",
      });
      return;
    }

    setSavingPassword(true);
    try {
      await completePasswordChange(newPassword, confirmPassword);
      setPasswordCode("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordStep("start");
      setPasswordNotice({
        tone: "success",
        text: "Your password has been changed.",
      });
    } catch (error) {
      setPasswordNotice({
        tone: "error",
        text: apiErrorMessage(error, "Your password could not be changed."),
      });
    } finally {
      setSavingPassword(false);
    }
  };

  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  const activeTab = ["details", "badges", "security"].includes(tab) 
    ? (tab as "details" | "badges" | "security") 
    : "details";

  const setActiveTab = (newTab: "details" | "badges" | "security") => {
    navigate({ search: { tab: newTab }, replace: true });
  };

  const handleLogout = async () => {
    await logout().catch(() => undefined);
    navigate({ to: "/login" });
  };

  if (currentUser.isLoading) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <LoaderCircle className="h-7 w-7 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-10">
      <header>
        <h1 className="flex items-center gap-3 font-display text-4xl tracking-tight sm:text-5xl">
          <UserRound className="h-8 w-8 shrink-0 text-accent sm:h-9 sm:w-9" />
          Profile
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Keep your details up to date so your learning experience fits you.
        </p>
      </header>

      <div className="flex flex-col gap-8">
        <nav className="app-scrollbar flex shrink-0 flex-row gap-2 overflow-x-auto border-b border-border pb-px">
          <button
            type="button"
            onClick={() => setActiveTab("details")}
            className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition ${
              activeTab === "details"
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
            }`}
          >
            <UserRound className="h-4 w-4" /> Personal details
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("badges")}
            className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition ${
              activeTab === "badges"
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
            }`}
          >
            <Award className="h-4 w-4" /> Course badges
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("security")}
            className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition ${
              activeTab === "security"
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
            }`}
          >
            <KeyRound className="h-4 w-4" /> Security & Plan
          </button>
        </nav>

        <div className="min-w-0 flex-1 space-y-6">
          <AnimatePresence mode="wait">
            {activeTab === "details" && (
              <motion.div
                key="details"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="space-y-6"
              >
                {!isEditingProfile ? (
                  <>
                    {/* Profile header (no solid box, directly on page background) */}
                    <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between py-2">
                      <div className="flex items-center gap-4">
                        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-accent/10 text-accent text-2xl font-bold">
                          {(name || "U").charAt(0).toUpperCase()}
                        </span>
                        <div>
                          <h2 className="font-display text-3xl tracking-tight sm:text-4xl text-foreground">
                            {name || "Your Name"}
                          </h2>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {user?.email || ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          onClick={() => setIsEditingProfile(true)}
                          className="h-10 rounded-full px-4 text-sm"
                        >
                          <Pencil className="mr-2 h-3.5 w-3.5" />
                          Edit profile
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={handleLogout}
                          className="h-10 rounded-full px-4 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                        >
                          <LogOut className="mr-2 h-3.5 w-3.5" />
                          Sign out
                        </Button>
                      </div>
                    </div>

                    {/* Detail cards */}
                    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      <ProfileInfoCard
                        label="Profile type"
                        value={PROFILE_TYPES.find(p => p.value === profileType)?.title || "Not selected"}
                        icon={PROFILE_TYPES.find(p => p.value === profileType)?.icon || UserRound}
                      />
                      {profileType === "student" && (
                        <>
                          <ProfileInfoCard label="Institution" value={institutionName || "Not set"} icon={School} />
                          <ProfileInfoCard label="Grade / Class" value={gradeOrClass || "Not set"} icon={Hash} />
                        </>
                      )}
                      {profileType === "professional" && (
                        <>
                          <ProfileInfoCard label="Organization" value={organizationName || "Not set"} icon={Building2} />
                          <ProfileInfoCard label="Role" value={professionalRole || "Not set"} icon={Briefcase} />
                          <ProfileInfoCard label="Experience" value={`${workExperience} year${workExperience === "1" ? "" : "s"}`} icon={Calendar} />
                        </>
                      )}
                    </section>

                    <NoticeMessage notice={profileNotice} />
                  </>
                ) : (
                  <form
                    onSubmit={handleProfileSubmit}
                    className="rounded-[24px] border border-border bg-card p-5 shadow-sm sm:p-7"
                  >
                    <div className="flex items-start gap-3">
                      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-accent/10 text-accent">
                        <UserRound className="h-5 w-5" />
                      </span>
                      <div>
                        <h2 className="font-display text-2xl tracking-tight">
                          Personal details
                        </h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Choose the option that best describes you.
                        </p>
                      </div>
                    </div>

                    <div className="mt-6 grid gap-5 sm:grid-cols-2">
                      <Field label="Name" htmlFor="profile-name">
                        <Input
                          id="profile-name"
                          value={name}
                          onChange={(event) => setName(event.target.value)}
                          maxLength={80}
                          placeholder="Enter your name"
                          autoComplete="name"
                          className="h-11 rounded-xl bg-background"
                          required
                        />
                      </Field>
                      <Field label="Email" htmlFor="profile-email">
                        <Input
                          id="profile-email"
                          value={user?.email ?? ""}
                          readOnly
                          disabled
                          className="h-11 rounded-xl bg-muted"
                        />
                      </Field>
                    </div>

                    <fieldset className="mt-6">
                      <legend className="text-sm font-medium">I am a</legend>
                      <div className="mt-2 grid gap-3 xl:grid-cols-3">
                        {PROFILE_TYPES.map((option) => {
                          const Icon = option.icon;
                          const selected = profileType === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => {
                                setProfileType(option.value);
                                setProfileNotice(null);
                              }}
                              className={`rounded-2xl border p-4 text-left transition ${
                                selected
                                  ? "border-accent bg-accent/10 ring-1 ring-accent"
                                  : "border-border bg-background hover:border-accent/45 hover:bg-muted"
                              }`}
                            >
                              <Icon
                                className={`h-5 w-5 ${selected ? "text-accent" : "text-muted-foreground"}`}
                              />
                              <span className="mt-3 block text-sm font-semibold">
                                {option.title}
                              </span>
                              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                                {option.description}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>

                    {profileType === "student" && (
                      <div className="mt-6 grid gap-5 rounded-2xl bg-muted/70 p-4 sm:grid-cols-2">
                        <Field label="School, college, or university" htmlFor="institution">
                          <Input
                            id="institution"
                            value={institutionName}
                            onChange={(event) => setInstitutionName(event.target.value)}
                            maxLength={120}
                            className="h-11 rounded-xl bg-card"
                            required
                          />
                        </Field>
                        <Field label="Grade or class" htmlFor="grade-class">
                          <Input
                            id="grade-class"
                            value={gradeOrClass}
                            onChange={(event) => setGradeOrClass(event.target.value)}
                            maxLength={80}
                            placeholder="Enter grade or class"
                            className="h-11 rounded-xl bg-card"
                            required
                          />
                        </Field>
                      </div>
                    )}

                    {profileType === "professional" && (
                      <div className="mt-6 grid gap-5 rounded-2xl bg-muted/70 p-4 sm:grid-cols-2">
                        <Field label="Organization name" htmlFor="organization">
                          <Input
                            id="organization"
                            value={organizationName}
                            onChange={(event) => setOrganizationName(event.target.value)}
                            maxLength={120}
                            className="h-11 rounded-xl bg-card"
                            required
                          />
                        </Field>
                        <Field label="Role or job title" htmlFor="professional-role">
                          <Input
                            id="professional-role"
                            value={professionalRole}
                            onChange={(event) => setProfessionalRole(event.target.value)}
                            maxLength={120}
                            placeholder="Enter role or job title"
                            className="h-11 rounded-xl bg-card"
                          />
                        </Field>
                        <Field label="Work experience (years)" htmlFor="work-experience">
                          <Input
                            id="work-experience"
                            type="number"
                            min={0}
                            max={70}
                            step={1}
                            value={workExperience}
                            onChange={(event) => setWorkExperience(event.target.value)}
                            className="h-11 rounded-xl bg-card"
                            required
                          />
                        </Field>
                      </div>
                    )}

                    {profileType === "independent" && (
                      <p className="mt-6 rounded-2xl bg-muted/70 px-4 py-3 text-sm leading-6 text-muted-foreground">
                        No school or workplace details are needed for an independent learner.
                      </p>
                    )}

                    <NoticeMessage notice={profileNotice} />

                    <div className="mt-6 flex justify-end gap-3">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setIsEditingProfile(false)}
                        className="h-11 rounded-full px-5"
                      >
                        Cancel
                      </Button>
                      <Button
                        type="submit"
                        disabled={savingProfile}
                        className="h-11 rounded-full px-5"
                      >
                        {savingProfile ? (
                          <LoaderCircle className="h-4 w-4 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4" />
                        )}
                        Save profile
                      </Button>
                    </div>
                  </form>
                )}
              </motion.div>
            )}

          {activeTab === "badges" && (
            <motion.section
              key="badges"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden rounded-[24px] border border-border bg-card p-5 shadow-sm sm:p-7"
            >
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-amber-400/20 text-amber-700 dark:text-amber-300">
                  <Award className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-display text-2xl tracking-tight">
                    Course badges
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Complete every activity in a course to earn its badge.
                  </p>
                </div>
              </div>

              {courses.isLoading && (
                <div className="mt-6 grid gap-3 xl:grid-cols-2">
                  {[0, 1].map((item) => (
                    <div
                      key={item}
                      className="h-32 animate-pulse rounded-2xl bg-muted"
                    />
                  ))}
                </div>
              )}

              {!courses.isLoading && earnedBadges.length === 0 && (
                <div className="mt-6 flex items-center gap-4 rounded-2xl border border-dashed border-border bg-background/45 p-5">
                  <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
                    <Award className="h-5 w-5" />
                  </span>
                  <div>
                    <div className="font-semibold">Your first badge is waiting</div>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      Finish a learning path to add a course badge here.
                    </p>
                  </div>
                </div>
              )}

              {earnedBadges.length > 0 && (
                <div className="mt-6 grid gap-3 xl:grid-cols-2">
                  {earnedBadges.map((course, index) => (
                    <motion.div
                      key={course.session_id}
                      initial={{ opacity: 0, y: 10, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ delay: index * 0.05 }}
                    >
                      <Link
                        to="/app/session/$id/path"
                        params={{ id: course.session_id }}
                        className="group flex h-full items-center gap-4 rounded-2xl border border-amber-400/40 bg-gradient-to-br from-amber-400/20 via-background/70 to-accent/10 p-4 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-elegant)]"
                      >
                        <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-amber-400 text-amber-950 shadow-sm">
                          <Award className="h-7 w-7" />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[11px] font-bold uppercase tracking-[0.15em] text-amber-700 dark:text-amber-300">
                            Course completed
                          </span>
                          <span className="mt-1 block line-clamp-2 font-display text-xl leading-tight tracking-tight">
                            {course.topic}
                          </span>
                          <span className="mt-1 block text-xs text-muted-foreground">
                            {course.total_modules} modules mastered
                          </span>
                        </span>
                      </Link>
                    </motion.div>
                  ))}
                </div>
              )}
            </motion.section>
          )}

          {activeTab === "security" && (
            <motion.div
              key="security"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="space-y-6"
            >
              <section className="rounded-[24px] border border-border bg-card p-5 shadow-sm sm:p-7">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-display text-2xl tracking-tight">Plan</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {user?.plan === "pro"
                        ? "Pro — unlimited course generations."
                        : user?.plan === "plus"
                          ? "Plus — up to 20 course generations per 24 hours."
                          : "Free — 5 Quick and 3 Deep Focus course generations per 24 hours."}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="rounded-full bg-accent/10 px-4 py-1.5 text-sm font-semibold uppercase tracking-wide text-accent">
                      {user?.plan === "pro"
                        ? "Pro"
                        : user?.plan === "plus"
                          ? "Plus"
                          : "Free"}
                    </span>
                    <Link
                      to="/app/pricing"
                      className="rounded-full bg-primary px-4 py-1.5 text-sm font-semibold uppercase tracking-wide text-primary-foreground shadow-sm transition hover:opacity-90"
                    >
                      Upgrade
                    </Link>
                  </div>
                </div>
              </section>

              <form
                onSubmit={handlePasswordSubmit}
                className="rounded-[24px] border border-border bg-card p-5 shadow-sm sm:p-7"
              >
                <div className="flex items-start gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
                    <KeyRound className="h-5 w-5" />
                  </span>
                  <div>
                    <h2 className="font-display text-2xl tracking-tight">
                      Change password
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Verify a one-time code sent to your email before choosing a new
                      password.
                    </p>
                  </div>
                </div>

                <div className="mt-6 grid gap-5">
                  {passwordStep === "start" && (
                    <p className="rounded-2xl bg-muted/70 px-4 py-3 text-sm text-muted-foreground">
                      We will send a short verification code to {user?.email}.
                    </p>
                  )}
                  {passwordStep === "verify" && (
                    <Field label="Verification code" htmlFor="password-code">
                      <Input
                        id="password-code"
                        value={passwordCode}
                        onChange={(event) =>
                          setPasswordCode(
                            event.target.value.replace(/\D/g, "").slice(0, 4),
                          )
                        }
                        placeholder="Enter 4-digit code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        className="h-11 rounded-xl bg-background"
                        required
                      />
                    </Field>
                  )}
                  {passwordStep === "new" && (
                    <div className="grid gap-5 sm:grid-cols-2">
                      <Field label="New password" htmlFor="new-password">
                        <PasswordInput
                          id="new-password"
                          value={newPassword}
                          onChange={(event) => setNewPassword(event.target.value)}
                          minLength={8}
                          maxLength={128}
                          autoComplete="new-password"
                          className="h-11 rounded-xl bg-background"
                          required
                        />
                      </Field>
                      <Field label="Confirm new password" htmlFor="confirm-password">
                        <PasswordInput
                          id="confirm-password"
                          value={confirmPassword}
                          onChange={(event) => setConfirmPassword(event.target.value)}
                          minLength={8}
                          maxLength={128}
                          autoComplete="new-password"
                          className="h-11 rounded-xl bg-background"
                          required
                        />
                      </Field>
                    </div>
                  )}
                </div>
                {passwordStep === "new" && (
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    Use at least 8 characters, including a letter and a number.
                  </p>
                )}

                <NoticeMessage notice={passwordNotice} />

                <div className="mt-6 flex justify-end">
                  <Button
                    type="submit"
                    disabled={savingPassword}
                    className="h-11 rounded-full px-5"
                  >
                    {savingPassword && (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    )}
                    {passwordStep === "start"
                      ? "Send code"
                      : passwordStep === "verify"
                        ? "Verify code"
                        : "Change password"}
                  </Button>
                </div>
              </form>
            </motion.div>
          )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}


function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function ProfileInfoCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: ComponentType<{ className?: string }>;
}) {
  return (
    <article className="rounded-[20px] border border-border bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <span className="grid h-9 w-9 place-items-center rounded-full bg-accent/10 text-accent">
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-3 font-display text-xl tracking-tight">{value}</p>
    </article>
  );
}

function PasswordInput(props: React.ComponentProps<typeof Input>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input
        {...props}
        type={visible ? "text" : "password"}
        className={`${props.className ?? ""} pr-11`}
      />
      <button
        type="button"
        onClick={() => setVisible((value) => !value)}
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute inset-y-0 right-3 grid place-items-center text-muted-foreground hover:text-foreground"
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

function NoticeMessage({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return (
    <p
      role={notice.tone === "error" ? "alert" : "status"}
      className={`mt-5 flex items-start gap-2 rounded-2xl px-4 py-3 text-sm ${
        notice.tone === "success"
          ? "bg-primary/10 text-primary"
          : "bg-destructive/10 text-destructive"
      }`}
    >
      {notice.tone === "success" && (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      )}
      {notice.text}
    </p>
  );
}
