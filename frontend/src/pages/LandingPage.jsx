import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileText, Download, BookOpen, Users, ArrowRight, CheckCircle, Shield, Eye, EyeOff, Mail, Lock, User, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";
import { toast } from "sonner";
import { API } from "@/App";

export default function LandingPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [showAuth, setShowAuth] = useState(false);
  const [authMode, setAuthMode] = useState("login"); // login or register
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    name: ""
  });
  const navigate = useNavigate();

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  const handlePopularClick = (clause) => {
    navigate(`/search?q=${encodeURIComponent(clause)}`);
  };

  const handleAuth = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const endpoint = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload = authMode === "login" 
        ? { email: formData.email, password: formData.password }
        : { email: formData.email, password: formData.password, name: formData.name };

      const response = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload)
      });

      let data;
      try {
        data = await response.json();
      } catch (parseError) {
        console.error("Failed to parse response:", parseError);
        toast.error("Server error. Please try again.");
        return;
      }

      if (response.ok) {
        toast.success(authMode === "login" ? "Welcome back!" : "Account created successfully!");
        navigate("/dashboard", { state: { user: data }, replace: true });
      } else {
        toast.error(data.detail || "Authentication failed");
      }
    } catch (error) {
      console.error("Auth error:", error);
      toast.error("Network error. Please check your connection.");
    } finally {
      setLoading(false);
    }
  };

  const popularClauses = [
    "FAR 52.212-4",
    "DFARS 252.204-7012",
    "FAR 52.219-8"
  ];

  const features = [
    {
      icon: Search,
      title: "Smart Clause Search",
      description: "Instantly find any FAR, DFARS, or agency-specific clause with our intelligent search."
    },
    {
      icon: FileText,
      title: "Contract Analysis",
      description: "Upload contracts and automatically compare clauses against official requirements."
    },
    {
      icon: Download,
      title: "Flowdown Analysis",
      description: "Identify which clauses must flow down to subcontractors based on contract details."
    }
  ];

  const benefits = [
    { icon: Shield, text: "NIST 800-171 Ready" },
    { icon: BookOpen, text: "Full FAR/DFARS Coverage" },
    { icon: Users, text: "Trusted by Contractors" },
    { icon: CheckCircle, text: "AI-Powered Analysis" }
  ];

  return (
    <div className="min-h-screen app-background">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 navbar border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <ClauseGuardLogo className="w-9 h-9" variant="dark" />
              <span className="font-semibold text-xl text-white tracking-tight">ClauseGuard</span>
            </div>
            <div className="flex items-center gap-3">
              <Button 
                variant="ghost" 
                className="text-white/80 hover:text-white hover:bg-white/10 font-medium"
                onClick={() => navigate("/search")}
                data-testid="nav-search-btn"
              >
                Search Clauses
              </Button>
              <Button 
                onClick={() => setShowAuth(true)}
                className="bg-teal-500 hover:bg-teal-600 text-white font-medium px-5 shadow-lg shadow-teal-500/20"
                data-testid="nav-login-btn"
              >
                Sign In
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-gradient pt-32 pb-20">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24 relative z-10">
          {/* Trust Badge */}
          <div className="flex justify-center mb-8 animate-fade-in-up">
            <div className="glass-dark rounded-full px-5 py-2 text-white/90 text-sm font-medium flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-soft"></div>
              Trusted by 500+ Government Contractors
            </div>
          </div>

          {/* Heading */}
          <div className="text-center max-w-4xl mx-auto mb-10 animate-fade-in-up animation-delay-100">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 tracking-tight">
              Navigate Federal Clauses
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-teal-300 to-cyan-300">
                with Confidence
              </span>
            </h1>
            <p className="text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
              The intelligent platform for searching, analyzing, and managing FAR/DFARS 
              clauses. Stay compliant, save time, win more contracts.
            </p>
          </div>

          {/* Search Box */}
          <div className="max-w-2xl mx-auto mb-8 animate-fade-in-up animation-delay-200">
            <form onSubmit={handleSearch} className="relative">
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <Input
                type="text"
                placeholder="Search FAR, DFARS, or specific clause numbers..."
                className="search-input-hero pl-14 pr-32 h-14 text-base"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="hero-search-input"
              />
              <Button 
                type="submit" 
                className="absolute right-2 top-1/2 -translate-y-1/2 bg-teal-600 hover:bg-teal-700 text-white font-medium px-6 h-10 shadow-lg"
                data-testid="hero-search-btn"
              >
                Search
              </Button>
            </form>
          </div>

          {/* Popular Searches */}
          <div className="flex flex-wrap justify-center gap-3 mb-12 animate-fade-in-up animation-delay-300">
            <span className="text-slate-400 text-sm">Popular:</span>
            {popularClauses.map((clause) => (
              <button
                key={clause}
                onClick={() => handlePopularClick(clause)}
                className="text-sm text-teal-300 hover:text-white bg-white/5 hover:bg-white/10 px-3 py-1.5 rounded-full transition-all duration-200"
                data-testid={`popular-clause-${clause.replace(/\s+/g, '-')}`}
              >
                {clause}
              </button>
            ))}
          </div>

          {/* Benefits */}
          <div className="flex flex-wrap justify-center gap-6 animate-fade-in-up animation-delay-400">
            {benefits.map((benefit, index) => (
              <div key={index} className="flex items-center gap-2 text-slate-300">
                <benefit.icon className="w-4 h-4 text-teal-400" />
                <span className="text-sm font-medium">{benefit.text}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-slate-800 mb-4 tracking-tight">
              Everything You Need for Compliance
            </h2>
            <p className="text-slate-500 max-w-xl mx-auto">
              Powerful tools to help you navigate federal acquisition regulations with ease.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {features.map((feature, index) => (
              <div
                key={index}
                className="feature-card animate-fade-in-up"
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <div className="icon-wrapper mb-5">
                  <feature.icon className="w-6 h-6 text-teal-600" />
                </div>
                <h3 className="text-lg font-semibold text-slate-800 mb-2">{feature.title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="modern-card-elevated p-10 text-center bg-gradient-to-br from-slate-50 to-teal-50/30">
            <h2 className="text-2xl font-bold text-slate-800 mb-3">
              Ready to Streamline Your Compliance?
            </h2>
            <p className="text-slate-500 mb-6 max-w-lg mx-auto">
              Join hundreds of contractors who trust ClauseGuard for their federal clause management.
            </p>
            <Button 
              onClick={() => setShowAuth(true)}
              className="bg-teal-600 hover:bg-teal-700 text-white font-medium px-8 py-2.5 h-auto text-base shadow-lg shadow-teal-500/20"
              data-testid="cta-get-started-btn"
            >
              Get Started Free
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-10 px-6 border-t border-slate-200/60">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <ClauseGuardLogo className="w-6 h-6" />
            <span className="font-semibold text-slate-700">ClauseGuard</span>
          </div>
          <p className="text-sm text-slate-500">
            © {new Date().getFullYear()} ClauseGuard. Federal Clause Management Made Simple.
          </p>
        </div>
      </footer>

      {/* Auth Modal */}
      {showAuth && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
            onClick={() => setShowAuth(false)}
          />
          
          {/* Modal */}
          <div className="auth-card relative animate-fade-in-up">
            {/* Close button */}
            <button
              onClick={() => setShowAuth(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* Header */}
            <div className="text-center mb-8">
              <ClauseGuardLogo className="w-12 h-12 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-slate-800">
                {authMode === "login" ? "Welcome back" : "Create an account"}
              </h2>
              <p className="text-slate-500 mt-1">
                {authMode === "login" 
                  ? "Sign in to access your dashboard" 
                  : "Get started with ClauseGuard"}
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleAuth} className="space-y-4">
              {authMode === "register" && (
                <div>
                  <label className="form-label">Full Name</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <Input
                      type="text"
                      placeholder="John Doe"
                      className="input-modern pl-11"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      required
                      data-testid="auth-name-input"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="form-label">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <Input
                    type="email"
                    placeholder="you@company.com"
                    className="input-modern pl-11"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    required
                    data-testid="auth-email-input"
                  />
                </div>
              </div>

              <div>
                <label className="form-label">Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <Input
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    className="input-modern pl-11 pr-11"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                    minLength={6}
                    data-testid="auth-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-medium h-11 mt-2"
                disabled={loading}
                data-testid="auth-submit-btn"
              >
                {loading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  authMode === "login" ? "Sign In" : "Create Account"
                )}
              </Button>
            </form>

            {/* Switch mode */}
            <div className="mt-6 text-center text-sm">
              <span className="text-slate-500">
                {authMode === "login" ? "Don't have an account?" : "Already have an account?"}
              </span>
              <button
                type="button"
                onClick={() => {
                  setAuthMode(authMode === "login" ? "register" : "login");
                  setFormData({ email: "", password: "", name: "" });
                }}
                className="ml-1 text-teal-600 hover:text-teal-700 font-medium"
                data-testid="auth-switch-mode"
              >
                {authMode === "login" ? "Sign up" : "Sign in"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
