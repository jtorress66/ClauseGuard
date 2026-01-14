import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileText, Download, Shield, BookOpen, Users, ArrowRight, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function LandingPage() {
  const [searchQuery, setSearchQuery] = useState("");
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

  const handleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
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
      description: "Instantly find any FAR, DFARS, or agency-specific clause with our intelligent search. Always up-to-date with the latest regulatory changes."
    },
    {
      icon: FileText,
      title: "Contract Upload & Compare",
      description: "Upload your contracts and automatically compare your clauses against the official Federal Acquisition Regulation requirements."
    },
    {
      icon: Download,
      title: "Flowdown Analysis",
      description: "Identify which clauses must flow down to subcontractors based on contract type, value, and specific requirements."
    }
  ];

  const benefits = [
    { icon: Shield, text: "NIST 800-171 Compliance Ready" },
    { icon: BookOpen, text: "Complete FAR/DFARS Coverage" },
    { icon: Users, text: "Trusted by 500+ Contractors" },
    { icon: CheckCircle, text: "AI-Powered Analysis" }
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 navbar bg-navy-900/80 border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <Shield className="w-8 h-8 text-teal-400" />
              <span className="font-heading font-bold text-xl text-white">ClauseGuard</span>
            </div>
            <div className="flex items-center gap-4">
              <Button 
                variant="ghost" 
                className="text-white/80 hover:text-white hover:bg-white/10"
                onClick={() => navigate("/search")}
                data-testid="nav-search-btn"
              >
                Search Clauses
              </Button>
              <Button 
                onClick={handleLogin}
                className="bg-teal-600 hover:bg-teal-700 text-white btn-press"
                data-testid="nav-login-btn"
              >
                Sign In with Google
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-section hero-gradient pt-32 pb-24">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24 relative z-10">
          {/* Trust Badge */}
          <div className="flex justify-center mb-8 animate-fade-in-up">
            <div className="glass rounded-full px-6 py-2 text-white/90 text-sm font-medium border border-white/20">
              Trusted by 500+ Government Contractors
            </div>
          </div>

          {/* Main Heading */}
          <div className="text-center max-w-4xl mx-auto mb-12">
            <h1 className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl text-white mb-4 animate-fade-in-up animation-delay-100">
              Master Federal Clauses
            </h1>
            <h2 className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl text-teal-400 mb-8 animate-fade-in-up animation-delay-200">
              With Confidence
            </h2>
            <p className="text-lg text-white/80 max-w-2xl mx-auto animate-fade-in-up animation-delay-300">
              Search, compare, and analyze Federal Acquisition Regulation clauses. Ensure compliance and streamline your contract management workflow.
            </p>
          </div>

          {/* Search Bar */}
          <form onSubmit={handleSearch} className="max-w-2xl mx-auto animate-fade-in-up animation-delay-400">
            <div className="search-container glass rounded-xl p-2 border border-white/20">
              <div className="flex gap-2">
                <Input
                  type="text"
                  placeholder="Search FAR, DFARS, or clause number..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="flex-1 h-12 bg-white/95 border-0 text-navy-900 placeholder:text-navy-400 rounded-lg search-input"
                  data-testid="hero-search-input"
                />
                <Button 
                  type="submit" 
                  className="h-12 px-8 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg btn-press"
                  data-testid="hero-search-btn"
                >
                  Search Clauses
                </Button>
              </div>
            </div>
          </form>

          {/* Popular Searches */}
          <div className="flex flex-wrap justify-center gap-4 mt-8 animate-fade-in-up animation-delay-400">
            <span className="text-white/60 text-sm">Popular:</span>
            {popularClauses.map((clause) => (
              <button
                key={clause}
                onClick={() => handlePopularClick(clause)}
                className="text-white/80 hover:text-white text-sm popular-tag px-3 py-1 rounded-full border border-white/20"
                data-testid={`popular-clause-${clause.replace(/\s+/g, '-')}`}
              >
                {clause}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 bg-slate-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="text-center mb-16">
            <h2 className="font-heading font-bold text-3xl sm:text-4xl text-navy-900 mb-4">
              Everything You Need for Clause Compliance
            </h2>
            <p className="text-lg text-navy-600 max-w-2xl mx-auto">
              Powerful tools designed for government contractors to navigate complex federal regulations with ease.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <div 
                key={feature.title}
                className="feature-card bg-white rounded-xl p-8 border border-slate-200 hover:border-teal-200"
                data-testid={`feature-card-${index}`}
              >
                <div className="feature-icon mb-6">
                  <feature.icon className="w-7 h-7" />
                </div>
                <h3 className="font-heading font-bold text-xl text-navy-900 mb-3">
                  {feature.title}
                </h3>
                <p className="text-navy-600 leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {benefits.map((benefit, index) => (
              <div 
                key={benefit.text}
                className="flex flex-col items-center text-center"
                data-testid={`benefit-${index}`}
              >
                <div className="w-14 h-14 rounded-full bg-teal-100 flex items-center justify-center mb-4">
                  <benefit.icon className="w-7 h-7 text-teal-700" />
                </div>
                <span className="text-navy-800 font-medium">{benefit.text}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 hero-gradient">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24 text-center">
          <h2 className="font-heading font-bold text-3xl sm:text-4xl text-white mb-6">
            Ready to Simplify Compliance?
          </h2>
          <p className="text-lg text-white/80 mb-8 max-w-xl mx-auto">
            Join hundreds of government contractors who trust ClauseGuard for their federal clause management.
          </p>
          <Button 
            onClick={handleLogin}
            size="lg"
            className="bg-teal-500 hover:bg-teal-600 text-white font-medium px-8 py-6 text-lg rounded-xl btn-press"
            data-testid="cta-get-started-btn"
          >
            Get Started Free
            <ArrowRight className="ml-2 w-5 h-5" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-navy-950 py-12">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Shield className="w-6 h-6 text-teal-400" />
              <span className="font-heading font-bold text-white">ClauseGuard</span>
            </div>
            <p className="text-white/60 text-sm">
              © 2025 ClauseGuard. Helping contractors navigate federal regulations.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
