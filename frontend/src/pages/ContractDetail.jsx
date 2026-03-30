import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  ArrowLeft, FileText, Download, Sparkles, 
  CheckCircle, AlertTriangle, Loader2, ListChecks, BarChart, RefreshCw, Trash2, FileJson
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
  const [rescanning, setRescanning] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [generatingChecklist, setGeneratingChecklist] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [agiloftExtraction, setAgiloftExtraction] = useState(null);

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
    toast.info("AI Analysis started. This may take 1-2 minutes...", { duration: 5000 });
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 minute timeout
      
      const response = await fetch(`${API}/contracts/${contractId}/analyze`, {
        method: "POST",
        credentials: "include",
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        const data = await response.json();
        setContract(prev => ({ ...prev, analysis_result: data.analysis }));
        toast.success("Analysis complete");
      } else {
        const errorData = await response.text();
        console.error("Analysis response error:", errorData);
        toast.error(`Analysis failed: ${response.status}`);
      }
    } catch (error) {
      console.error("Analysis error:", error);
      if (error.name === 'AbortError') {
        toast.error("Analysis timed out. Please try again.");
      } else {
        toast.error(`Analysis failed: ${error.message}`);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const rescanClauses = async () => {
    setRescanning(true);
    try {
      const response = await fetch(`${API}/contracts/${contractId}/rescan`, {
        method: "POST",
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setContract(prev => ({ ...prev, clauses_found: data.clauses_found }));
        
        if (data.needs_reupload) {
          toast.error(data.warning, { duration: 10000 });
        } else if (data.warning) {
          toast.warning(data.warning);
        } else {
          toast.success(data.message);
        }
        
        if (data.removed_clauses && data.removed_clauses.length > 0) {
          toast.info(`Removed ${data.removed_clauses.length} referenced (non-header) clauses`);
        }
      } else {
        toast.error("Rescan failed");
      }
    } catch (error) {
      toast.error("Rescan failed");
    } finally {
      setRescanning(false);
    }
  };

  const deleteContract = async () => {
    if (!confirm("Are you sure you want to delete this contract? This action cannot be undone.")) return;
    
    try {
      const response = await fetch(`${API}/contracts/${contractId}`, {
        method: "DELETE",
        credentials: "include"
      });
      if (response.ok) {
        toast.success("Contract deleted");
        navigate("/dashboard");
      } else {
        toast.error("Failed to delete contract");
      }
    } catch (error) {
      toast.error("Failed to delete contract");
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

  const extractForAgiloft = async () => {
    setExtracting(true);
    try {
      const response = await fetch(`${API}/contracts/${contractId}/extract-for-agiloft`, {
        method: "POST",
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setAgiloftExtraction(data);
        toast.success(`Extracted ${data.extraction?.summary?.total_selected_sub_clauses || 0} selected clauses`);
      } else {
        toast.error("Failed to extract clauses");
      }
    } catch (error) {
      toast.error("Failed to extract clauses");
    } finally {
      setExtracting(false);
    }
  };

  const downloadAgiloftJson = async () => {
    try {
      const response = await fetch(`${API}/contracts/${contractId}/export-clauses-json`, {
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `agiloft_clauses_${contract?.filename || contractId}.json`;
        a.click();
        window.URL.revokeObjectURL(url);
        toast.success("JSON file downloaded");
      } else {
        toast.error("Failed to download JSON");
      }
    } catch (error) {
      toast.error("Failed to download JSON");
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
              <Button 
                variant="outline" 
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                onClick={deleteContract} 
                data-testid="delete-contract-btn"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
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
                onClick={rescanClauses}
                disabled={rescanning}
                variant="outline"
                data-testid="rescan-btn"
                title="Re-detect clause headers (ignores referenced clauses)"
              >
                {rescanning ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Rescanning...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Rescan Clauses
                  </>
                )}
              </Button>
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
              <Button
                onClick={extractForAgiloft}
                disabled={extracting}
                variant="outline"
                className="border-teal-600 text-teal-600 hover:bg-teal-50"
                data-testid="extract-agiloft-btn"
              >
                {extracting ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <FileJson className="w-4 h-4 mr-2" />
                )}
                Extract for Agiloft
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
                          <li key={i} className="text-sm text-red-700">
                            • {typeof clause === 'object' 
                                ? `${clause.clause || clause.title || ''} ${clause.why_missing ? `- ${clause.why_missing}` : ''}`
                                : clause}
                          </li>
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
                          <li key={i} className="text-sm text-amber-700">
                            • {typeof gap === 'object' ? (gap.description || gap.gap || JSON.stringify(gap)) : gap}
                          </li>
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
                          <li key={i} className="text-sm text-teal-700">
                            • {typeof rec === 'object' ? (rec.recommendation || rec.action || JSON.stringify(rec)) : rec}
                          </li>
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

            {/* Agiloft Extraction Results */}
            {agiloftExtraction && (
              <div className="bg-white rounded-xl border border-teal-200">
                <div className="p-6 border-b border-teal-100 bg-teal-50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <FileJson className="w-5 h-5 text-teal-600" />
                      <h2 className="font-heading font-bold text-lg text-teal-900">
                        Agiloft Extraction Results
                      </h2>
                    </div>
                    <Button
                      onClick={downloadAgiloftJson}
                      size="sm"
                      className="bg-teal-600 hover:bg-teal-700"
                      data-testid="download-json-btn"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Download JSON
                    </Button>
                  </div>
                </div>
                
                <div className="p-6 space-y-6">
                  {/* Summary Stats */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-blue-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-blue-600">
                        {agiloftExtraction.extraction?.summary?.total_top_level_clauses || 0}
                      </p>
                      <p className="text-sm text-slate-600">Top-Level Clauses</p>
                    </div>
                    <div className="bg-green-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-green-600">
                        {agiloftExtraction.extraction?.summary?.total_selected_sub_clauses || 0}
                      </p>
                      <p className="text-sm text-slate-600">Selected Sub-Clauses (X)</p>
                    </div>
                    <div className="bg-teal-50 rounded-lg p-4">
                      <p className="text-2xl font-bold text-teal-600">
                        {agiloftExtraction.agiloft_upload_ready?.clauses?.length || 0}
                      </p>
                      <p className="text-sm text-slate-600">Total for Agiloft</p>
                    </div>
                  </div>

                  {/* Top-Level Clauses */}
                  {agiloftExtraction.extraction?.top_level_clauses?.length > 0 && (
                    <div>
                      <h3 className="font-semibold text-navy-900 mb-3 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-blue-600" />
                        Top-Level Clauses ({agiloftExtraction.extraction.top_level_clauses.length})
                      </h3>
                      <div className="max-h-48 overflow-y-auto space-y-2">
                        {agiloftExtraction.extraction.top_level_clauses.map((clause, i) => (
                          <div 
                            key={i}
                            className="flex items-start gap-3 p-3 bg-blue-50 rounded-lg border border-blue-200"
                          >
                            <FileText className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                            <div>
                              <span className="font-medium text-blue-800">{clause.number}</span>
                              {(clause.db_title || clause.title) && (
                                <p className="text-sm text-blue-700">{clause.db_title || clause.title}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Selected Sub-Clauses (Checked with X) */}
                  {agiloftExtraction.extraction?.selected_sub_clauses?.length > 0 && (
                    <div>
                      <h3 className="font-semibold text-navy-900 mb-3 flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-green-600" />
                        Selected Sub-Clauses (X marked) ({agiloftExtraction.extraction.selected_sub_clauses.length})
                      </h3>
                      <div className="max-h-64 overflow-y-auto space-y-2">
                        {agiloftExtraction.extraction.selected_sub_clauses.map((clause, i) => (
                          <div 
                            key={i}
                            className="flex items-start gap-3 p-3 bg-green-50 rounded-lg border border-green-200"
                          >
                            <CheckCircle className="w-4 h-4 text-green-600 mt-0.5 flex-shrink-0" />
                            <div>
                              <span className="font-medium text-green-800">{clause.number}</span>
                              {(clause.db_title || clause.title) && (
                                <p className="text-sm text-green-700">{clause.db_title || clause.title}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Parent Clauses with Selections */}
                  {Object.keys(agiloftExtraction.extraction?.parent_clauses_with_selections || {}).length > 0 && (
                    <div>
                      <h3 className="font-semibold text-navy-900 mb-3">Parent Clauses with Sub-selections</h3>
                      <div className="space-y-3">
                        {Object.entries(agiloftExtraction.extraction.parent_clauses_with_selections)
                          .filter(([_, data]) => data.selected_sub_clauses?.length > 0 || data.unselected_sub_clauses?.length > 0)
                          .map(([parentNum, data]) => (
                            <div key={parentNum} className="bg-slate-50 rounded-lg p-4">
                              <p className="font-medium text-navy-800 mb-2">
                                {parentNum} {data.title && `- ${data.title}`}
                              </p>
                              <p className="text-sm text-slate-600">
                                <span className="text-green-600 font-medium">{data.selected_sub_clauses?.length || 0} selected</span>
                                {" • "}
                                <span className="text-slate-500">{data.unselected_sub_clauses?.length || 0} unselected</span>
                              </p>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
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
