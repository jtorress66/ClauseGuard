import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ArrowLeft, FileText, Sparkles, Loader2, 
  CheckCircle, XCircle, ArrowRight, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";
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

export default function ContractComparison({ user }) {
  const navigate = useNavigate();
  const [contracts, setContracts] = useState([]);
  const [contract1Id, setContract1Id] = useState("");
  const [contract2Id, setContract2Id] = useState("");
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingContracts, setLoadingContracts] = useState(true);

  useEffect(() => {
    fetchContracts();
  }, []);

  const fetchContracts = async () => {
    try {
      const response = await fetch(`${API}/contracts/`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setContracts(data.contracts || []);
      }
    } catch (error) {
      toast.error("Failed to fetch contracts");
    } finally {
      setLoadingContracts(false);
    }
  };

  const runComparison = async () => {
    if (!contract1Id || !contract2Id) {
      toast.error("Please select two contracts to compare");
      return;
    }

    if (contract1Id === contract2Id) {
      toast.error("Please select two different contracts");
      return;
    }

    setLoading(true);
    setComparison(null);

    try {
      const response = await fetch(
        `${API}/contracts/compare?contract_id_1=${contract1Id}&contract_id_2=${contract2Id}`,
        {
          method: "POST",
          credentials: "include"
        }
      );

      if (response.ok) {
        const data = await response.json();
        setComparison(data.comparison);
        toast.success("Comparison complete");
      } else {
        toast.error("Comparison failed");
      }
    } catch (error) {
      toast.error("Comparison failed");
    } finally {
      setLoading(false);
    }
  };

  const getContract = (id) => contracts.find(c => c.contract_id === id);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center gap-4 h-16">
            <Button variant="ghost" size="icon" onClick={() => navigate(-1)} data-testid="back-btn">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate("/")}>
              <ClauseGuardLogo className="w-7 h-7" variant="light" />
              <span className="font-heading font-bold text-lg text-navy-900">ClauseGuard</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 md:px-12 py-8">
        <div className="mb-8">
          <h1 className="font-heading font-bold text-3xl text-navy-900 mb-2">
            Contract Comparison
          </h1>
          <p className="text-slate-600">
            Compare clauses and terms between two uploaded contracts using AI analysis
          </p>
        </div>

        {/* Contract Selection */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
          <h2 className="font-heading font-bold text-lg text-navy-900 mb-6">
            Select Contracts to Compare
          </h2>

          {loadingContracts ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
            </div>
          ) : contracts.length < 2 ? (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-500 mb-4">
                You need at least 2 contracts to compare. Currently you have {contracts.length}.
              </p>
              <Button onClick={() => navigate("/upload")} data-testid="upload-more-btn">
                Upload Contracts
              </Button>
            </div>
          ) : (
            <div className="flex flex-col md:flex-row items-center gap-4">
              <div className="flex-1 w-full">
                <label className="block text-sm font-medium text-navy-700 mb-2">
                  Contract 1
                </label>
                <Select value={contract1Id} onValueChange={setContract1Id}>
                  <SelectTrigger data-testid="contract1-select">
                    <SelectValue placeholder="Select first contract" />
                  </SelectTrigger>
                  <SelectContent>
                    {contracts.map(contract => (
                      <SelectItem key={contract.contract_id} value={contract.contract_id}>
                        {contract.name} ({contract.clauses_found?.length || 0} clauses)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="hidden md:flex items-center justify-center w-16">
                <ArrowRight className="w-6 h-6 text-slate-400" />
              </div>

              <div className="flex-1 w-full">
                <label className="block text-sm font-medium text-navy-700 mb-2">
                  Contract 2
                </label>
                <Select value={contract2Id} onValueChange={setContract2Id}>
                  <SelectTrigger data-testid="contract2-select">
                    <SelectValue placeholder="Select second contract" />
                  </SelectTrigger>
                  <SelectContent>
                    {contracts.map(contract => (
                      <SelectItem key={contract.contract_id} value={contract.contract_id}>
                        {contract.name} ({contract.clauses_found?.length || 0} clauses)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="w-full md:w-auto">
                <label className="block text-sm font-medium text-transparent mb-2 hidden md:block">
                  Action
                </label>
                <Button
                  onClick={runComparison}
                  disabled={loading || !contract1Id || !contract2Id}
                  className="w-full md:w-auto bg-purple-600 hover:bg-purple-700"
                  data-testid="compare-btn"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Comparing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 mr-2" />
                      Compare with AI
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Comparison Results */}
        {comparison && (
          <div className="space-y-6">
            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                <div className="text-3xl font-bold text-blue-600 mb-1">
                  {comparison.common_clauses?.length || 0}
                </div>
                <p className="text-sm text-slate-500">Common Clauses</p>
              </div>
              <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                <div className="text-3xl font-bold text-teal-600 mb-1">
                  {comparison.only_in_contract_1?.length || 0}
                </div>
                <p className="text-sm text-slate-500">Only in {getContract(contract1Id)?.name?.substring(0, 15) || "Contract 1"}</p>
              </div>
              <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                <div className="text-3xl font-bold text-amber-600 mb-1">
                  {comparison.only_in_contract_2?.length || 0}
                </div>
                <p className="text-sm text-slate-500">Only in {getContract(contract2Id)?.name?.substring(0, 15) || "Contract 2"}</p>
              </div>
            </div>

            {/* Common Clauses */}
            {comparison.common_clauses?.length > 0 && (
              <div className="bg-blue-50 rounded-xl border border-blue-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <CheckCircle className="w-6 h-6 text-blue-600" />
                  <h3 className="font-heading font-bold text-blue-800">Common Clauses</h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {comparison.common_clauses.map(clause => (
                    <Badge 
                      key={clause}
                      className="bg-blue-100 text-blue-700 border-blue-200 cursor-pointer"
                      onClick={() => navigate(`/search?q=${encodeURIComponent(clause)}`)}
                    >
                      {clause}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Only in Contract 1 */}
            {comparison.only_in_contract_1?.length > 0 && (
              <div className="bg-teal-50 rounded-xl border border-teal-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <FileText className="w-6 h-6 text-teal-600" />
                  <h3 className="font-heading font-bold text-teal-800">
                    Only in {getContract(contract1Id)?.name || "Contract 1"}
                  </h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {comparison.only_in_contract_1.map(clause => (
                    <Badge 
                      key={clause}
                      className="bg-teal-100 text-teal-700 border-teal-200 cursor-pointer"
                      onClick={() => navigate(`/search?q=${encodeURIComponent(clause)}`)}
                    >
                      {clause}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Only in Contract 2 */}
            {comparison.only_in_contract_2?.length > 0 && (
              <div className="bg-amber-50 rounded-xl border border-amber-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <FileText className="w-6 h-6 text-amber-600" />
                  <h3 className="font-heading font-bold text-amber-800">
                    Only in {getContract(contract2Id)?.name || "Contract 2"}
                  </h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {comparison.only_in_contract_2.map(clause => (
                    <Badge 
                      key={clause}
                      className="bg-amber-100 text-amber-700 border-amber-200 cursor-pointer"
                      onClick={() => navigate(`/search?q=${encodeURIComponent(clause)}`)}
                    >
                      {clause}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Key Differences */}
            {comparison.key_differences?.length > 0 && (
              <div className="bg-white rounded-xl border border-slate-200 p-6">
                <h3 className="font-heading font-bold text-navy-900 mb-4">Key Differences</h3>
                <ul className="space-y-2">
                  {comparison.key_differences.map((diff, i) => (
                    <li key={i} className="flex items-start gap-2 text-slate-700">
                      <XCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                      {diff}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommendations */}
            {comparison.recommendations?.length > 0 && (
              <div className="bg-green-50 rounded-xl border border-green-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <CheckCircle className="w-6 h-6 text-green-600" />
                  <h3 className="font-heading font-bold text-green-800">Recommendations</h3>
                </div>
                <ul className="space-y-2">
                  {comparison.recommendations.map((rec, i) => (
                    <li key={i} className="text-green-700">• {rec}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Raw comparison fallback */}
            {comparison.raw_comparison && !comparison.common_clauses && (
              <div className="bg-white rounded-xl border border-slate-200 p-6">
                <h3 className="font-heading font-bold text-navy-900 mb-4">AI Analysis</h3>
                <p className="text-slate-700 whitespace-pre-wrap">{comparison.raw_comparison}</p>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!comparison && !loading && contracts.length >= 2 && (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <RefreshCw className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="font-heading font-bold text-xl text-navy-900 mb-2">
              Ready to Compare
            </h3>
            <p className="text-slate-500">
              Select two contracts above and click "Compare with AI" to see the differences
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
