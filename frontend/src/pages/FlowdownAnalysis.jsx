import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Shield, Download, AlertTriangle, CheckCircle, 
  Info, ChevronDown, ChevronUp, FileText
} from "lucide-react";
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

export default function FlowdownAnalysis({ user }) {
  const navigate = useNavigate();
  const [contractType, setContractType] = useState("");
  const [contractValue, setContractValue] = useState("");
  const [selectedClauses, setSelectedClauses] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [contracts, setContracts] = useState([]);
  const [showClauseSelector, setShowClauseSelector] = useState(false);
  const [availableClauses, setAvailableClauses] = useState([]);

  useEffect(() => {
    fetchContracts();
    fetchClauses();
  }, []);

  const fetchContracts = async () => {
    try {
      const response = await fetch(`${API}/contracts/`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setContracts(data.contracts || []);
      }
    } catch (error) {
      console.error("Failed to fetch contracts");
    }
  };

  const fetchClauses = async () => {
    try {
      const response = await fetch(`${API}/clauses/search?query=&limit=100`);
      if (response.ok) {
        const data = await response.json();
        setAvailableClauses(data.clauses || []);
      }
    } catch (error) {
      console.error("Failed to fetch clauses");
    }
  };

  const loadFromContract = (contractId) => {
    const contract = contracts.find(c => c.contract_id === contractId);
    if (contract) {
      setSelectedClauses(contract.clauses_found || []);
      toast.success(`Loaded ${contract.clauses_found?.length || 0} clauses from contract`);
    }
  };

  const toggleClause = (clauseNumber) => {
    setSelectedClauses(prev => 
      prev.includes(clauseNumber)
        ? prev.filter(c => c !== clauseNumber)
        : [...prev, clauseNumber]
    );
  };

  const runAnalysis = async () => {
    if (!contractType || !contractValue || selectedClauses.length === 0) {
      toast.error("Please fill in all fields and select clauses");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API}/flowdown/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          contract_type: contractType,
          contract_value: parseFloat(contractValue),
          clauses: selectedClauses
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAnalysis(data);
        toast.success("Analysis complete");
      } else {
        toast.error("Analysis failed");
      }
    } catch (error) {
      toast.error("Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const contractTypes = [
    "Fixed-Price",
    "Cost-Reimbursement",
    "Time-and-Materials",
    "Labor-Hour",
    "Indefinite-Delivery",
    "R&D",
    "Supply",
    "Services"
  ];

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
              <Shield className="w-7 h-7 text-teal-600" />
              <span className="font-heading font-bold text-lg text-navy-900">ClauseGuard</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 md:px-12 py-8">
        <div className="mb-8">
          <h1 className="font-heading font-bold text-3xl text-navy-900 mb-2">
            Flowdown Analysis
          </h1>
          <p className="text-slate-600">
            Identify which clauses must flow down to subcontractors based on your contract
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Input Section */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h2 className="font-heading font-bold text-lg text-navy-900 mb-4">
                Contract Details
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-navy-700 mb-2">
                    Contract Type
                  </label>
                  <Select value={contractType} onValueChange={setContractType}>
                    <SelectTrigger data-testid="contract-type-select">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {contractTypes.map(type => (
                        <SelectItem key={type} value={type}>{type}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-navy-700 mb-2">
                    Contract Value ($)
                  </label>
                  <Input
                    type="number"
                    placeholder="e.g., 1000000"
                    value={contractValue}
                    onChange={(e) => setContractValue(e.target.value)}
                    data-testid="contract-value-input"
                  />
                </div>

                {contracts.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-navy-700 mb-2">
                      Load from Contract
                    </label>
                    <Select onValueChange={loadFromContract}>
                      <SelectTrigger data-testid="load-contract-select">
                        <SelectValue placeholder="Select a contract" />
                      </SelectTrigger>
                      <SelectContent>
                        {contracts.map(contract => (
                          <SelectItem key={contract.contract_id} value={contract.contract_id}>
                            {contract.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-sm font-medium text-navy-700">
                      Selected Clauses ({selectedClauses.length})
                    </label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowClauseSelector(!showClauseSelector)}
                    >
                      {showClauseSelector ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </Button>
                  </div>
                  
                  {showClauseSelector && (
                    <div className="max-h-60 overflow-y-auto border border-slate-200 rounded-lg p-2 space-y-1">
                      {availableClauses.map(clause => (
                        <label
                          key={clause.clause_id}
                          className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={selectedClauses.includes(clause.number)}
                            onChange={() => toggleClause(clause.number)}
                            className="rounded border-slate-300"
                          />
                          <span className="font-mono text-sm text-teal-700">{clause.number}</span>
                        </label>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-wrap gap-1 mt-2">
                    {selectedClauses.slice(0, 5).map(clause => (
                      <Badge key={clause} variant="secondary" className="text-xs">
                        {clause}
                      </Badge>
                    ))}
                    {selectedClauses.length > 5 && (
                      <Badge variant="outline" className="text-xs">
                        +{selectedClauses.length - 5} more
                      </Badge>
                    )}
                  </div>
                </div>

                <Button
                  onClick={runAnalysis}
                  disabled={loading || !contractType || !contractValue || selectedClauses.length === 0}
                  className="w-full bg-teal-600 hover:bg-teal-700"
                  data-testid="analyze-btn"
                >
                  {loading ? "Analyzing..." : "Run Flowdown Analysis"}
                </Button>
              </div>
            </div>

            {/* Info Card */}
            <div className="bg-blue-50 rounded-xl border border-blue-200 p-6">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h3 className="font-medium text-blue-800 mb-1">About Flowdown</h3>
                  <p className="text-sm text-blue-700">
                    Flowdown clauses are contract requirements that must be passed to subcontractors. 
                    The requirements vary based on contract type, value, and specific clause provisions.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Results Section */}
          <div className="lg:col-span-2">
            {!analysis ? (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <Download className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="font-heading font-bold text-xl text-navy-900 mb-2">
                  No Analysis Yet
                </h3>
                <p className="text-slate-500">
                  Enter contract details and run the analysis to see flowdown requirements
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Summary Cards */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                    <div className="text-3xl font-bold text-teal-600 mb-1">
                      {analysis.required_flowdown_clauses?.length || 0}
                    </div>
                    <p className="text-sm text-slate-500">Required Flowdown</p>
                  </div>
                  <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                    <div className="text-3xl font-bold text-green-600 mb-1">
                      {analysis.present_in_contract?.length || 0}
                    </div>
                    <p className="text-sm text-slate-500">Present in Contract</p>
                  </div>
                  <div className="bg-white rounded-xl border border-slate-200 p-6 text-center">
                    <div className="text-3xl font-bold text-red-600 mb-1">
                      {analysis.missing_from_contract?.length || 0}
                    </div>
                    <p className="text-sm text-slate-500">Missing</p>
                  </div>
                </div>

                {/* Missing Clauses Alert */}
                {analysis.missing_from_contract?.length > 0 && (
                  <div className="bg-red-50 rounded-xl border border-red-200 p-6">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="w-6 h-6 text-red-600 mt-0.5" />
                      <div>
                        <h3 className="font-heading font-bold text-red-800 mb-2">
                          Missing Flowdown Clauses
                        </h3>
                        <p className="text-sm text-red-700 mb-4">
                          The following clauses are required for flowdown but are not present in your contract:
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {analysis.missing_from_contract.map(clause => (
                            <Badge 
                              key={clause} 
                              className="bg-red-100 text-red-700 border-red-200 cursor-pointer"
                              onClick={() => navigate(`/search?q=${encodeURIComponent(clause)}`)}
                            >
                              {clause}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Present Clauses */}
                {analysis.present_in_contract?.length > 0 && (
                  <div className="bg-green-50 rounded-xl border border-green-200 p-6">
                    <div className="flex items-start gap-3">
                      <CheckCircle className="w-6 h-6 text-green-600 mt-0.5" />
                      <div>
                        <h3 className="font-heading font-bold text-green-800 mb-2">
                          Compliant Clauses
                        </h3>
                        <p className="text-sm text-green-700 mb-4">
                          These required flowdown clauses are present in your contract:
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {analysis.present_in_contract.map(clause => (
                            <Badge 
                              key={clause} 
                              className="bg-green-100 text-green-700 border-green-200"
                            >
                              {clause}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Detailed Clause List */}
                <div className="bg-white rounded-xl border border-slate-200">
                  <div className="p-6 border-b border-slate-100">
                    <h3 className="font-heading font-bold text-lg text-navy-900">
                      Flowdown Clause Details
                    </h3>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {analysis.clause_details?.map(clause => (
                      <div 
                        key={clause.clause_id} 
                        className="p-4 hover:bg-slate-50 cursor-pointer"
                        onClick={() => navigate(`/clause/${clause.clause_id}`)}
                      >
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-mono font-semibold text-teal-700">
                                {clause.number}
                              </span>
                              <Badge variant="secondary">{clause.type}</Badge>
                              {analysis.present_in_contract?.includes(clause.number) ? (
                                <CheckCircle className="w-4 h-4 text-green-500" />
                              ) : (
                                <AlertTriangle className="w-4 h-4 text-red-500" />
                              )}
                            </div>
                            <p className="text-navy-900 font-medium">{clause.title}</p>
                            <p className="text-sm text-slate-500 mt-1">{clause.summary}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
