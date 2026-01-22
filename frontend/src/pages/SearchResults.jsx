import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Star, ArrowLeft, Sparkles, Save, BookOpen, ExternalLink, Database, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function SearchResults() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [clauseType, setClauseType] = useState(searchParams.get("type") || "All");
  const [useAI, setUseAI] = useState(searchParams.get("ai") === "true");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) {
      setQuery(q);
      performSearch(q, searchParams.get("type") || "All", searchParams.get("ai") === "true");
    }
  }, [searchParams]);

  const checkAuth = async () => {
    try {
      const response = await fetch(`${API}/auth/me`, { credentials: "include" });
      setIsAuthenticated(response.ok);
    } catch {
      setIsAuthenticated(false);
    }
  };

  const performSearch = async (searchQuery, type, aiSearch) => {
    if (!searchQuery.trim()) return;
    
    setLoading(true);
    setAiAnalysis(null);
    
    try {
      // For AI search, always attempt it first - let the backend handle auth
      // This ensures we don't rely on potentially stale isAuthenticated state
      let url;
      if (aiSearch) {
        url = `${API}/clauses/ai-search?query=${encodeURIComponent(searchQuery)}`;
      } else {
        url = `${API}/clauses/search?query=${encodeURIComponent(searchQuery)}`;
        if (type && type !== "All") {
          url += `&clause_type=${encodeURIComponent(type)}`;
        }
      }

      const response = await fetch(url, { credentials: "include" });
      
      if (response.ok) {
        const data = await response.json();
        setResults(data.clauses || []);
        if (data.ai_analysis) {
          setAiAnalysis(data.ai_analysis);
        }
        // Update auth state if we successfully hit AI search
        if (aiSearch) {
          setIsAuthenticated(true);
        }
      } else if (response.status === 401 && aiSearch) {
        toast.error("Please sign in to use AI search");
        setUseAI(false);
        setIsAuthenticated(false);
        // Fall back to regular search
        performSearch(searchQuery, type, false);
        return;
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(errorData.detail || "Search failed");
      }
    } catch (error) {
      console.error("Search error:", error);
      toast.error("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setSearchParams({ q: query, type: clauseType, ai: useAI.toString() });
  };

  const handleSaveSearch = async () => {
    if (!isAuthenticated) {
      toast.error("Please sign in to save searches");
      return;
    }

    try {
      const response = await fetch(`${API}/user/saved-searches?query=${encodeURIComponent(query)}`, {
        method: "POST",
        credentials: "include"
      });
      
      if (response.ok) {
        toast.success("Search saved!");
      } else {
        toast.error("Failed to save search");
      }
    } catch (error) {
      toast.error("Failed to save search");
    }
  };

  const handleAddFavorite = async (clauseId) => {
    if (!isAuthenticated) {
      toast.error("Please sign in to add favorites");
      return;
    }

    try {
      const response = await fetch(`${API}/user/favorites?clause_id=${clauseId}`, {
        method: "POST",
        credentials: "include"
      });
      
      if (response.ok) {
        toast.success("Added to favorites!");
      } else {
        toast.error("Failed to add favorite");
      }
    } catch (error) {
      toast.error("Failed to add favorite");
    }
  };

  return (
    <div className="min-h-screen app-background-soft">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center gap-4 h-16">
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => navigate(-1)}
              className="hover:bg-slate-100"
              data-testid="back-btn"
            >
              <ArrowLeft className="w-5 h-5 text-slate-600" />
            </Button>
            
            <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => navigate("/")}>
              <ClauseGuardLogo className="w-8 h-8" variant="light" />
              <span className="font-semibold text-xl text-slate-800 tracking-tight">ClauseGuard</span>
            </div>
          </div>
        </div>
      </header>

      {/* Search Section */}
      <div className="bg-white border-b border-slate-200/60 py-6">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <form onSubmit={handleSearch} className="flex flex-col md:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <Input
                type="text"
                placeholder="Search FAR, DFARS, or clause number..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-12 h-12 text-base bg-slate-50/80 border-slate-200 rounded-xl focus:bg-white"
                data-testid="search-input"
              />
            </div>
            
            <Select value={clauseType} onValueChange={setClauseType}>
              <SelectTrigger className="w-full md:w-36 h-12 rounded-xl border-slate-200" data-testid="type-filter">
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent className="rounded-xl">
                <SelectItem value="All">All Types</SelectItem>
                <SelectItem value="FAR">FAR</SelectItem>
                <SelectItem value="DFARS">DFARS</SelectItem>
              </SelectContent>
            </Select>

            <Button
              type="button"
              variant={useAI ? "default" : "outline"}
              className={`h-12 rounded-xl px-5 ${useAI 
                ? "bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 shadow-md shadow-purple-200" 
                : "border-slate-200 hover:bg-slate-50"}`}
              onClick={() => {
                // Toggle AI mode and immediately trigger search if there's a query
                const newAiState = !useAI;
                setUseAI(newAiState);
                if (query.trim()) {
                  // Update URL params and trigger search
                  setSearchParams({ q: query, type: clauseType, ai: newAiState.toString() });
                }
              }}
              data-testid="ai-toggle"
            >
              <Sparkles className={`w-4 h-4 mr-2 ${useAI ? "" : "text-purple-500"}`} />
              AI Search
            </Button>
            
            <Button 
              type="submit" 
              className="h-12 px-8 rounded-xl bg-teal-600 hover:bg-teal-700 shadow-sm" 
              data-testid="search-btn"
            >
              Search
            </Button>
          </form>

          {query && (
            <div className="flex items-center gap-4 mt-4">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-slate-400" />
                <span className="text-sm text-slate-500">
                  {results.length} results for "{query}"
                </span>
                <span className="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full">
                  Source: acquisition.gov
                </span>
              </div>
              {isAuthenticated && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={handleSaveSearch}
                  className="text-teal-600 hover:text-teal-700 hover:bg-teal-50"
                  data-testid="save-search-btn"
                >
                  <Save className="w-4 h-4 mr-1.5" />
                  Save Search
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {/* AI Analysis Banner */}
        {useAI && aiAnalysis && (
          <div className="modern-card bg-gradient-to-r from-violet-50 to-purple-50 border-violet-200/60 p-6 mb-8" data-testid="ai-analysis">
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 bg-gradient-to-br from-violet-500 to-purple-500 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg shadow-purple-200">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="font-semibold text-slate-800">AI Search Results</h3>
                  <span className="text-xs bg-white/80 text-purple-600 px-2 py-0.5 rounded-full border border-purple-200">
                    Indexed Data Only
                  </span>
                </div>
                <p className="text-slate-600 text-sm">{aiAnalysis}</p>
                <p className="text-xs text-slate-400 mt-2 flex items-center gap-1">
                  <ExternalLink className="w-3 h-3" />
                  Results sourced from clauses indexed from acquisition.gov
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-10 h-10 text-teal-600 animate-spin mb-4" />
            <p className="text-slate-500">Searching clauses...</p>
          </div>
        )}

        {/* No Results */}
        {!loading && query && results.length === 0 && (
          <div className="text-center py-20">
            <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Search className="w-8 h-8 text-slate-300" />
            </div>
            <h3 className="font-semibold text-slate-700 mb-2">No clauses found</h3>
            <p className="text-slate-500 text-sm mb-6 max-w-md mx-auto">
              No matching clauses found in the indexed acquisition.gov data. 
              Try different keywords or sync more clauses from acquisition.gov.
            </p>
            <Button 
              variant="outline" 
              onClick={() => navigate("/dashboard")}
              className="rounded-xl"
            >
              Go to Dashboard
            </Button>
          </div>
        )}

        {/* Results List */}
        {!loading && results.length > 0 && (
          <div className="space-y-4">
            {results.map((clause) => (
              <div
                key={clause.clause_id}
                className="modern-card p-6 hover:border-teal-200 cursor-pointer group"
                onClick={() => navigate(`/clause/${clause.clause_id}`)}
                data-testid={`clause-${clause.clause_id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-3 flex-wrap">
                      <span className="font-mono text-lg font-semibold text-teal-700">
                        {clause.number}
                      </span>
                      <Badge 
                        className={clause.type === "FAR" 
                          ? "bg-blue-100 text-blue-700 border-blue-200" 
                          : "bg-purple-100 text-purple-700 border-purple-200"}
                      >
                        {clause.type}
                      </Badge>
                      {clause.flowdown_required && (
                        <Badge className="bg-amber-50 text-amber-700 border-amber-200">
                          Flowdown Required
                        </Badge>
                      )}
                      {clause.source && (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" />
                          {clause.source}
                        </span>
                      )}
                    </div>
                    
                    <h3 className="font-semibold text-slate-800 mb-2 group-hover:text-teal-700 transition-colors">
                      {clause.title}
                    </h3>
                    
                    <p className="text-slate-500 text-sm line-clamp-2 mb-3">
                      {clause.summary || (clause.text ? clause.text.substring(0, 200) + "..." : "Click to view full clause text")}
                    </p>

                    {/* AI Explanation - Only shown for AI search */}
                    {clause.ai_explanation && (
                      <div className="flex items-start gap-2 bg-gradient-to-r from-violet-50 to-purple-50 rounded-lg p-3 mt-3 border border-violet-100">
                        <Sparkles className="w-4 h-4 text-purple-500 flex-shrink-0 mt-0.5" />
                        <p className="text-purple-700 text-sm">{clause.ai_explanation}</p>
                      </div>
                    )}

                    {clause.keywords?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-3">
                        {clause.keywords.slice(0, 5).map((keyword) => (
                          <span 
                            key={keyword}
                            className="text-xs bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full"
                          >
                            {keyword}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAddFavorite(clause.clause_id);
                    }}
                    className="text-slate-300 hover:text-amber-500 hover:bg-amber-50"
                    data-testid={`favorite-${clause.clause_id}`}
                  >
                    <Star className="w-5 h-5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
