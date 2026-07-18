import { createFileRoute } from "@tanstack/react-router";
import { Check } from "lucide-react";

export const Route = createFileRoute("/app/pricing")({
  head: () => ({ meta: [{ title: "Pricing - Lexinit" }] }),
  component: PricingPage,
});

function PricingPage() {
  const plans = [
    {
      name: "Free",
      price: "₹0",
      description: "For trying the full learning loop.",
      action: "Current plan",
      available: false,
      isCurrent: true,
      features: [
        "Access to all learning content",
        "5 Quick generations per 24 hours",
        "Community support",
        "3 Deep Focus generations per 24 hours",
      ],
    },
    {
      name: "Pro",
      price: "₹49",
      description: "For learners who generate often.",
      action: "Coming soon",
      available: false,
      featured: true,
      features: [
        "Full access to all features",
        "Limited to 20 generations for 24 hours",
        "Priority support",
        "Deep focus mode with advanced AI",
      ],
    },
    {
      name: "Premium",
      price: "₹99",
      description: "For heavier study and exam prep.",
      action: "Coming soon",
      available: false,
      features: [
        "Access to all learning content",
        "Unlimited Generations",
        "Exclusive support",
        "Deep focus mode with advanced AI",
      ],
    },
  ];

  return (
    <div className="mx-auto max-w-6xl pb-12 pt-4">
      <header className="mb-10 max-w-2xl">
        <h1 className="font-display text-4xl tracking-tight sm:text-5xl">
          Upgrade your learning
        </h1>
        <p className="mt-4 text-sm leading-6 text-muted-foreground">
          You are currently on the Free plan. More advanced plans are coming soon to support heavier study sessions and exam preparation.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`relative rounded-3xl border bg-card p-6 transition-shadow sm:p-8 ${
              plan.featured
                ? "border-accent shadow-[var(--shadow-glow)]"
                : "border-border"
            }`}
          >
            {plan.isCurrent && (
              <div className="absolute -top-3 left-6 rounded-full border border-border bg-muted px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Current Plan
              </div>
            )}
            {plan.featured && !plan.isCurrent && (
              <div className="absolute -top-3 left-6 rounded-full bg-accent px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-accent-foreground">
                Most Popular
              </div>
            )}
            <h3 className="font-display text-2xl tracking-tight">
              {plan.name}
            </h3>
            <p className="mt-2 min-h-10 text-sm text-muted-foreground">
              {plan.description}
            </p>
            <div className="mt-6 flex items-end gap-1 border-b border-border pb-6">
              <span className="font-display text-5xl tracking-tight">
                {plan.price}
              </span>
              <span className="pb-1.5 text-xs text-muted-foreground">
                / month
              </span>
            </div>
            <ul className="mt-6 space-y-3 text-sm">
              {plan.features.map((feature) => (
                <li key={feature} className="flex items-start gap-3">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <span className="text-muted-foreground">{feature}</span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              disabled={!plan.available}
              className={`mt-8 inline-flex w-full items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition ${
                plan.isCurrent
                  ? "cursor-default border border-border bg-muted text-muted-foreground"
                  : plan.available
                    ? "bg-primary text-primary-foreground hover:opacity-90"
                    : "cursor-not-allowed border border-border bg-background/50 text-muted-foreground"
              }`}
            >
              {plan.action}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
