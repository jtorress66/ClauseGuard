import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Filter, Star, BookOpen, Shield, ArrowLeft, Sparkles, Save, X } from "lucide-react";
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
      let url;
      if (aiSearch && isAuthenticated) {
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
      } else if (response.status === 401 && aiSearch) {
        toast.error("Please sign in to use AI search");
        setUseAI(false);
        performSearch(searchQuery, type, false);
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
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center gap-4 h-16">
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => navigate(-1)}
              data-testid="back-btn"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            
            <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate("/")}>
              <Shield className="w-7 h-7 text-teal-600" />
              <span className="font-heading font-bold text-lg text-navy-900">ClauseGuard</span>
            </div>
          </div>
        </div>
      </header>

      {/* Search Section */}
      <div className="bg-white border-b border-slate-200 py-6">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <form onSubmit={handleSearch} className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <Input
                type="text"
                placeholder="Search FAR, DFARS, or clause number..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-12 h-12 text-lg"
                data-testid="search-input"
              />
            </div>
            
            <Select value={clauseType} onValueChange={setClauseType}>
              <SelectTrigger className="w-full md:w-40 h-12" data-testid="type-filter">
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="All">All Types</SelectItem>
                <SelectItem value="FAR">FAR</SelectItem>
                <SelectItem value="DFARS">DFARS</SelectItem>
              </SelectContent>
            </Select>

            <Button
              type="button"
              variant={useAI ? "default" : "outline"}
              className={`h-12 ${useAI ? "bg-purple-600 hover:bg-purple-700" : ""}`}
              onClick={() => setUseAI(!useAI)}
              data-testid="ai-toggle"
            >
              <Sparkles className="w-4 h-4 mr-2" />
              AI Search
            </Button>
            
            <Button type="submit" className="h-12 px-8 bg-teal-600 hover:bg-teal-700" data-testid="search-btn">
              Search
            </Button>
          </form>

          {query && (
            <div className="flex items-center gap-4 mt-4">
              <span className="text-sm text-slate-500">
                {results.length} results for "{query}"
              </span>
              {isAuthenticated && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={handleSaveSearch}
                  className="text-teal-600"
                  data-testid="save-search-btn"
                >
                  <Save className="w-4 h-4 mr-1" />
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
        {aiAnalysis && (
          <div className="bg-purple-50 border border-purple-200 rounded-xl p-6 mb-8" data-testid="ai-analysis">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <h3 className="font-heading font-bold text-purple-900 mb-2">AI Analysis</h3>
                <p className="text-purple-800 text-sm whitespace-pre-wrap">{aiAnalysis}</p>
              </div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-teal-600 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}

        {/* Results List */}
        {!loading && results.length > 0 && (
          <div className="space-y-4">
            {results.map((clause) => (
              <div
                key={clause.clause_id}
                className="clause-card bg-white rounded-xl border border-slate-200 p-6 hover:shadow-md transition-all cursor-pointer"
                onClick={() => navigate(`/clause/${clause.clause_id}`)}
                data-testid={`clause-${clause.clause_id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="font-mono text-lg font-semibold text-teal-700">
                        {clause.number}
                      </span>
                      <Badge 
                        variant="secondary"
                        className={clause.type === "FAR" ? "status-far text-white" : "status-dfars text-white"}
                      >
                        {clause.type}
                      </Badge>
                      {clause.flowdown_required && (
                        <Badge variant="outline" className="border-amber-300 text-amber-700 bg-amber-50">
                          Flowdown Required
                        </Badge>
                      )}
                    </div>
                    
                    <h3 className="font-heading font-semibold text-navy-900 mb-2">
                      {clause.title}
                    </h3>
                    
                    <p className="text-slate-600 text-sm line-clamp-2 mb-3">
                      {clause.summary || clause.text?.substring(0, 200)}...
                    </p>

                    {clause.ai_explanation && (
                      <p className="text-purple-700 text-sm bg-purple-50 rounded-lg p-3">
                        <Sparkles className="w-4 h-4 inline mr-1" />
                        {clause.ai_explanation}
                      </p>
                    )}

                    {clause.keywords?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-3">
                        {clause.keywords.slice(0, 5).map((keyword) => (
                          <span 
                            key={keyword}
                            className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded"
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
                    className="text-slate-400 hover:text-amber-500"
                    data-testid={`favorite-${clause.clause_id}`}
                  >
                    <Star className="w-5 h-5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && results.length === 0 && query && (
          <div className="text-center py-20">
            <BookOpen className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="font-heading font-bold text-xl text-navy-900 mb-2">No clauses found</h3>
            <p className="text-slate-500 mb-6">
              Try adjusting your search terms or filters
            </p>
            <Button onClick={() => setQuery("")} variant="outline">
              Clear Search
            </Button>
          </div>
        )}

        {/* Initial State */}
        {!loading && results.length === 0 && !query && (
          <div className="text-center py-20">
            <Search className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="font-heading font-bold text-xl text-navy-900 mb-2">Search Federal Clauses</h3>
            <p className="text-slate-500">
              Enter a clause number, keyword, or topic to search
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
