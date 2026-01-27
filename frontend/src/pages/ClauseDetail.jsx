import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Star, FileText, Download, 
  MessageSquare, Plus, Trash2, ExternalLink, Copy, Check, LayoutDashboard
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function ClauseDetail() {
  const { clauseId } = useParams();
  const navigate = useNavigate();
  const [clause, setClause] = useState(null);
  const [loading, setLoading] = useState(true);
  const [annotations, setAnnotations] = useState([]);
  const [newAnnotation, setNewAnnotation] = useState("");
  const [showAnnotationForm, setShowAnnotationForm] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    checkAuth();
    fetchClause();
  }, [clauseId]);

  const checkAuth = async () => {
    try {
      const response = await fetch(`${API}/auth/me`, { credentials: "include" });
      if (response.ok) {
        setIsAuthenticated(true);
        fetchAnnotations();
        checkFavorite();
      }
    } catch {
      setIsAuthenticated(false);
    }
  };

  const fetchClause = async () => {
    try {
      const response = await fetch(`${API}/clauses/${clauseId}`);
      if (response.ok) {
        const data = await response.json();
        setClause(data);
      } else {
        toast.error("Clause not found");
        navigate("/search");
      }
    } catch (error) {
      toast.error("Failed to load clause");
    } finally {
      setLoading(false);
    }
  };

  const fetchAnnotations = async () => {
    try {
      const response = await fetch(`${API}/user/annotations?clause_id=${clauseId}`, {
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setAnnotations(data.annotations || []);
      }
    } catch (error) {
      console.error("Failed to fetch annotations");
    }
  };

  const checkFavorite = async () => {
    try {
      const response = await fetch(`${API}/user/favorites`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        const found = data.favorites?.some(f => f.clause_id === clauseId);
        setIsFavorite(found);
      }
    } catch (error) {
      console.error("Failed to check favorites");
    }
  };

  const toggleFavorite = async () => {
    if (!isAuthenticated) {
      toast.error("Please sign in to add favorites");
      return;
    }

    try {
      if (isFavorite) {
        await fetch(`${API}/user/favorites/${clauseId}`, {
          method: "DELETE",
          credentials: "include"
        });
        setIsFavorite(false);
        toast.success("Removed from favorites");
      } else {
        await fetch(`${API}/user/favorites?clause_id=${clauseId}`, {
          method: "POST",
          credentials: "include"
        });
        setIsFavorite(true);
        toast.success("Added to favorites");
      }
    } catch (error) {
      toast.error("Failed to update favorites");
    }
  };

  const addAnnotation = async () => {
    if (!newAnnotation.trim()) return;

    try {
      const response = await fetch(`${API}/user/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          clause_id: clauseId,
          note: newAnnotation
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAnnotations([...annotations, data]);
        setNewAnnotation("");
        setShowAnnotationForm(false);
        toast.success("Note added");
      }
    } catch (error) {
      toast.error("Failed to add note");
    }
  };

  const deleteAnnotation = async (annotationId) => {
    try {
      const response = await fetch(`${API}/user/annotations/${annotationId}`, {
        method: "DELETE",
        credentials: "include"
      });

      if (response.ok) {
        setAnnotations(annotations.filter(a => a.annotation_id !== annotationId));
        toast.success("Note deleted");
      }
    } catch (error) {
      toast.error("Failed to delete note");
    }
  };

  const copyClauseNumber = () => {
    navigator.clipboard.writeText(clause?.number || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("Clause number copied");
  };

  const exportToPdf = async () => {
    if (!isAuthenticated) {
      toast.error("Please sign in to export");
      return;
    }

    try {
      const response = await fetch(`${API}/export/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ clauses: [clause.number] })
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `clause_${clause.number.replace(/\./g, "_")}.pdf`;
        a.click();
        toast.success("PDF downloaded");
      }
    } catch (error) {
      toast.error("Failed to export PDF");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-teal-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!clause) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon" onClick={() => navigate(-1)} data-testid="back-btn">
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate("/")}>
                <ClauseGuardLogo className="w-7 h-7" variant="light" />
                <span className="font-heading font-bold text-lg text-navy-900">ClauseGuard</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isAuthenticated && (
                <Button
                  variant="outline"
                  onClick={() => navigate("/dashboard")}
                  className="gap-2"
                  data-testid="dashboard-btn"
                >
                  <LayoutDashboard className="w-4 h-4" />
                  Dashboard
                </Button>
              )}
              <Button
                variant="outline"
                onClick={toggleFavorite}
                className={isFavorite ? "text-amber-500 border-amber-300" : ""}
                data-testid="favorite-btn"
              >
                <Star className={`w-4 h-4 mr-2 ${isFavorite ? "fill-amber-500" : ""}`} />
                {isFavorite ? "Saved" : "Save"}
              </Button>
              <Button variant="outline" onClick={exportToPdf} data-testid="export-btn">
                <Download className="w-4 h-4 mr-2" />
                Export PDF
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Clause Content */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl border border-slate-200 p-8">
              {/* Clause Header */}
              <div className="mb-6">
                <div className="flex items-center gap-3 mb-4">
                  <button
                    onClick={copyClauseNumber}
                    className="flex items-center gap-2 font-mono text-2xl font-bold text-teal-700 hover:text-teal-800"
                    data-testid="clause-number"
                  >
                    {clause.number}
                    {copied ? (
                      <Check className="w-5 h-5 text-green-500" />
                    ) : (
                      <Copy className="w-5 h-5 text-slate-400" />
                    )}
                  </button>
                  <Badge 
                    className={clause.type === "FAR" ? "status-far text-white" : "status-dfars text-white"}
                  >
                    {clause.type}
                  </Badge>
                </div>
                
                <h1 className="font-heading font-bold text-2xl text-navy-900 mb-4">
                  {clause.title}
                </h1>

                <div className="flex flex-wrap gap-2">
                  {clause.flowdown_required && (
                    <Badge variant="outline" className="border-amber-300 text-amber-700 bg-amber-50">
                      Flowdown Required
                    </Badge>
                  )}
                  {clause.threshold_amount > 0 && (
                    <Badge variant="outline">
                      Threshold: ${clause.threshold_amount.toLocaleString()}
                    </Badge>
                  )}
                  {clause.contract_types?.map((type) => (
                    <Badge key={type} variant="secondary">
                      {type}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Summary */}
              {clause.summary && (
                <div className="mb-6 p-4 bg-teal-50 rounded-lg border border-teal-100">
                  <h3 className="font-semibold text-teal-800 mb-2">Summary</h3>
                  <p className="text-teal-700">{clause.summary}</p>
                </div>
              )}

              {/* Full Text */}
              <div>
                <h3 className="font-heading font-semibold text-navy-900 mb-4">Full Text</h3>
                <div className="prose prose-slate max-w-none">
                  <p className="text-slate-700 whitespace-pre-wrap leading-relaxed">
                    {clause.text}
                  </p>
                </div>
              </div>

              {/* Keywords */}
              {clause.keywords?.length > 0 && (
                <div className="mt-6 pt-6 border-t border-slate-100">
                  <h3 className="font-semibold text-navy-900 mb-3">Keywords</h3>
                  <div className="flex flex-wrap gap-2">
                    {clause.keywords.map((keyword) => (
                      <span
                        key={keyword}
                        className="text-sm bg-slate-100 text-slate-600 px-3 py-1 rounded-full cursor-pointer hover:bg-slate-200"
                        onClick={() => navigate(`/search?q=${encodeURIComponent(keyword)}`)}
                      >
                        {keyword}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* External Link */}
              <div className="mt-6 pt-6 border-t border-slate-100">
                <a
                  href={`https://www.acquisition.gov/far/${clause.number}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-teal-600 hover:text-teal-700"
                >
                  <ExternalLink className="w-4 h-4" />
                  View on acquisition.gov
                </a>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Annotations */}
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="flex items-center justify-between p-6 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <MessageSquare className="w-5 h-5 text-amber-500" />
                  <h2 className="font-heading font-bold text-lg text-navy-900">My Notes</h2>
                </div>
                {isAuthenticated && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowAnnotationForm(!showAnnotationForm)}
                    data-testid="add-note-btn"
                  >
                    <Plus className="w-4 h-4" />
                  </Button>
                )}
              </div>

              <div className="p-4">
                {!isAuthenticated ? (
                  <p className="text-slate-500 text-sm text-center py-4">
                    Sign in to add personal notes
                  </p>
                ) : (
                  <>
                    {showAnnotationForm && (
                      <div className="mb-4 p-4 bg-amber-50 rounded-lg border border-amber-200">
                        <Textarea
                          placeholder="Add a note about this clause..."
                          value={newAnnotation}
                          onChange={(e) => setNewAnnotation(e.target.value)}
                          className="mb-3"
                          data-testid="annotation-input"
                        />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={addAnnotation} data-testid="save-note-btn">
                            Save Note
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setShowAnnotationForm(false);
                              setNewAnnotation("");
                            }}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}

                    {annotations.length === 0 ? (
                      <p className="text-slate-500 text-sm text-center py-4">
                        No notes yet. Add your first note above.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {annotations.map((annotation) => (
                          <div
                            key={annotation.annotation_id}
                            className="p-3 bg-slate-50 rounded-lg"
                          >
                            <p className="text-sm text-navy-800 mb-2">{annotation.note}</p>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-slate-400">
                                {new Date(annotation.created_at).toLocaleDateString()}
                              </span>
                              <button
                                onClick={() => deleteAnnotation(annotation.annotation_id)}
                                className="text-slate-400 hover:text-red-500"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Related Info */}
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h3 className="font-heading font-bold text-navy-900 mb-4">Clause Information</h3>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Type</dt>
                  <dd className="font-medium text-navy-900">{clause.type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Flowdown</dt>
                  <dd className="font-medium text-navy-900">
                    {clause.flowdown_required ? "Required" : "Not Required"}
                  </dd>
                </div>
                {clause.threshold_amount > 0 && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Threshold</dt>
                    <dd className="font-medium text-navy-900">
                      ${clause.threshold_amount.toLocaleString()}
                    </dd>
                  </div>
                )}
                {clause.effective_date && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Effective</dt>
                    <dd className="font-medium text-navy-900">
                      {new Date(clause.effective_date).toLocaleDateString()}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
