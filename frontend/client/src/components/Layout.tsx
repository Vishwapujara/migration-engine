import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { GitBranch, LayoutDashboard, FileCode2 } from "lucide-react";

const nav = [
  { to: "/", label: "New Migration", icon: GitBranch },
  { to: "/jobs", label: "Jobs", icon: LayoutDashboard },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold text-primary">
            <FileCode2 className="h-5 w-5" />
            Migration Engine
          </Link>
          <nav className="flex items-center gap-4">
            {nav.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className={cn(
                  "flex items-center gap-1.5 text-sm transition-colors hover:text-primary",
                  pathname === to ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">{children}</main>

      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        Migration Engine — powered by LangGraph + Gemini
      </footer>
    </div>
  );
}
