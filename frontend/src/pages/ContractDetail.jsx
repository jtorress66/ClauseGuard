import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  ArrowLeft, FileText, Download, Sparkles, 
  CheckCircle, AlertTriangle, Loader2, ListChecks, BarChart
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function ContractDetail({ user }) {
  const { contractId } = useParams();
  const navigate = useNavigate();
  const [contract, setContract] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [generatingChecklist, setGeneratingChecklist] = useState(false);

  useEffect(() => {
    fetchContract();
  }, [contractId]);

  const fetchContract = async () => {
    try {
      const response = await fetch(`${API}/contracts/${contractId}`, {
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setContract(data);
      } else {
        toast.error("Contract not found");
        navigate("/dashboard");
      }
    } catch (error) {
      toast.error("Failed to load contract");
    } finally {
      setLoading(false);
    }
  };

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const response = await fetch(`${API}/contracts/${contractId}/analyze`, {
        method: "POST",
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setContract(prev => ({ ...prev, analysis_result: data.analysis }));
        toast.success("Analysis complete");
      } else {
        toast.error("Analysis failed");
      }
    } catch (error) {
      toast.error("Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const generateChecklist = async () => {
    setGeneratingChecklist(true);
    try {
      const response = await fetch(`${API}/checklist/generate?contract_id=${contractId}`, {
        method: "POST",
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setChecklist(data);
        toast.success("Checklist generated");
      } else {
        toast.error("Failed to generate checklist");
      }
    } catch (error) {
      toast.error("Failed to generate checklist");
    } finally {
      setGeneratingChecklist(false);
    }
  };

  const updateChecklistItem = async (index, status) => {
    if (!checklist) return;

    try {
      const response = await fetch(
        `${API}/checklist/${checklist.checklist_id}/item/${index}?status=${status}`,
        {
          method: "PUT",
          credentials: "include"
        }
      );
      if (response.ok) {
        setChecklist(prev => ({
          ...prev,
          items: prev.items.map((item, i) => 
            i === index ? { ...item, status } : item
          )
        }));
      }
    } catch (error) {
      toast.error("Failed to update checklist");
    }
  };

  const exportPdf = async () => {
    if (!contract?.clauses_found?.length) {
      toast.error("No clauses to export");
      return;
    }

    try {
      const response = await fetch(`${API}/export/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ clauses: contract.clauses_found })
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `contract_analysis_${contract.name}.pdf`;
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

  if (!contract) return null;

  const analysis = contract.analysis_result;
  const completedItems = checklist?.items?.filter(i => i.status === "completed").length || 0;
  const totalItems = checklist?.items?.length || 0;

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
              <Button variant="outline" onClick={exportPdf} data-testid="export-btn">
                <Download className="w-4 h-4 mr-2" />
                Export PDF
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {/* Contract Header */}
        <div className="bg-white rounded-xl border border-slate-200 p-8 mb-8">
          <div className="flex items-start gap-6">
            <div className="w-16 h-16 bg-slate-100 rounded-xl flex items-center justify-center">
              <FileText className="w-8 h-8 text-slate-500" />
            </div>
            <div className="flex-1">
              <h1 className="font-heading font-bold text-2xl text-navy-900 mb-2">
                {contract.name}
              </h1>
              <div className="flex items-center gap-4 text-sm text-slate-500">
                <span>Uploaded {new Date(contract.created_at).toLocaleDateString()}</span>
                <span>•</span>
                <span>{contract.clauses_found?.length || 0} clauses identified</span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={runAnalysis}
                disabled={analyzing}
                className="bg-purple-600 hover:bg-purple-700"
                data-testid="analyze-btn"
              >
                {analyzing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    AI Analysis
                  </>
                )}
              </Button>
              <Button
                onClick={generateChecklist}
                disabled={generatingChecklist}
                variant="outline"
                data-testid="checklist-btn"
              >
                {generatingChecklist ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <ListChecks className="w-4 h-4 mr-2" />
                )}
                Generate Checklist
              </Button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content Area */}
          <div className="lg:col-span-2 space-y-6">
            {/* AI Analysis Results */}
            {analysis && (
              <div className="bg-white rounded-xl border border-slate-200">
                <div className="p-6 border-b border-slate-100 flex items-center gap-3">
                  <Sparkles className="w-5 h-5 text-purple-600" />
                  <h2 className="font-heading font-bold text-lg text-navy-900">AI Analysis Results</h2>
                </div>
                
                <div className="p-6 space-y-6">
                  {/* Risk Level */}
                  {analysis.risk_level && (
                    <div className="flex items-center gap-4">
                      <span className="text-slate-600">Risk Level:</span>
                      <Badge className={
                        analysis.risk_level === "High" ? "bg-red-100 text-red-700" :
                        analysis.risk_level === "Medium" ? "bg-amber-100 text-amber-700" :
                        "bg-green-100 text-green-700"
                      }>
                        {analysis.risk_level}
                      </Badge>
                    </div>
                  )}

                  {/* Summary */}
                  {analysis.summary && (
                    <div>
                      <h3 className="font-semibold text-navy-900 mb-2">Summary</h3>
                      <p className="text-slate-600">{analysis.summary}</p>
                    </div>
                  )}

                  {/* Missing Clauses */}
                  {analysis.missing_clauses?.length > 0 && (
                    <div className="bg-red-50 rounded-lg p-4 border border-red-200">
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle className="w-5 h-5 text-red-600" />
                        <h3 className="font-semibold text-red-800">Missing Required Clauses</h3>
                      </div>
                      <ul className="space-y-1">
                        {analysis.missing_clauses.map((clause, i) => (
                          <li key={i} className="text-sm text-red-700">• {clause}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Compliance Gaps */}
                  {analysis.compliance_gaps?.length > 0 && (
                    <div className="bg-amber-50 rounded-lg p-4 border border-amber-200">
                      <h3 className="font-semibold text-amber-800 mb-3">Compliance Gaps</h3>
                      <ul className="space-y-1">
                        {analysis.compliance_gaps.map((gap, i) => (
                          <li key={i} className="text-sm text-amber-700">• {gap}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Recommendations */}
                  {analysis.recommendations?.length > 0 && (
                    <div className="bg-teal-50 rounded-lg p-4 border border-teal-200">
                      <div className="flex items-center gap-2 mb-3">
                        <CheckCircle className="w-5 h-5 text-teal-600" />
                        <h3 className="font-semibold text-teal-800">Recommendations</h3>
                      </div>
                      <ul className="space-y-1">
                        {analysis.recommendations.map((rec, i) => (
                          <li key={i} className="text-sm text-teal-700">• {rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Raw Analysis Fallback */}
                  {analysis.raw_analysis && !analysis.summary && (
                    <div className="prose prose-slate max-w-none">
                      <p className="whitespace-pre-wrap text-slate-600">{analysis.raw_analysis}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Identified Clauses */}
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="p-6 border-b border-slate-100">
                <h2 className="font-heading font-bold text-lg text-navy-900">
                  Identified Clauses ({contract.clauses_found?.length || 0})
                </h2>
              </div>
              
              <div className="p-6">
                {contract.clauses_found?.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {contract.clauses_found.map(clause => (
                      <Badge 
                        key={clause}
                        variant="outline"
                        className="cursor-pointer hover:bg-teal-50"
                        onClick={() => navigate(`/search?q=${encodeURIComponent(clause)}`)}
                      >
                        {clause}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-center py-4">
                    No standard clauses identified in this contract
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Compliance Checklist */}
            {checklist && (
              <div className="bg-white rounded-xl border border-slate-200">
                <div className="p-6 border-b border-slate-100">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <ListChecks className="w-5 h-5 text-teal-600" />
                      <h2 className="font-heading font-bold text-lg text-navy-900">Checklist</h2>
                    </div>
                    <span className="text-sm text-slate-500">
                      {completedItems}/{totalItems}
                    </span>
                  </div>
                  <Progress value={(completedItems / totalItems) * 100} className="h-2" />
                </div>
                
                <div className="max-h-96 overflow-y-auto">
                  {checklist.items?.map((item, index) => (
                    <div 
                      key={index}
                      className={`p-4 border-b border-slate-100 last:border-0 checklist-item ${
                        item.status === "completed" ? "bg-green-50" : ""
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <button
                          onClick={() => updateChecklistItem(
                            index, 
                            item.status === "completed" ? "pending" : "completed"
                          )}
                          className={`mt-1 w-5 h-5 rounded border flex items-center justify-center ${
                            item.status === "completed" 
                              ? "bg-green-500 border-green-500 text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {item.status === "completed" && <CheckCircle className="w-3 h-3" />}
                        </button>
                        <div>
                          <span className="font-mono text-xs text-teal-700">{item.clause_number}</span>
                          <p className={`text-sm ${item.status === "completed" ? "text-slate-400 line-through" : "text-navy-900"}`}>
                            {item.requirement}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick Actions */}
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h3 className="font-heading font-bold text-navy-900 mb-4">Quick Actions</h3>
              <div className="space-y-2">
                <Button 
                  variant="outline" 
                  className="w-full justify-start"
                  onClick={() => navigate(`/flowdown`)}
                >
                  <BarChart className="w-4 h-4 mr-2" />
                  Run Flowdown Analysis
                </Button>
                <Button 
                  variant="outline" 
                  className="w-full justify-start"
                  onClick={() => navigate("/upload")}
                >
                  <FileText className="w-4 h-4 mr-2" />
                  Compare with Another
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
