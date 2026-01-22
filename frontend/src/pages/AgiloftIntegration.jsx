import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Database, RefreshCw, CheckCircle, 
  AlertCircle, Loader2, Settings, Link2, Upload,
  FileText, AlertTriangle, ArrowUpRight, Download,
  Check, X, Search
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function AgiloftIntegration({ user }) {
  const navigate = useNavigate();
  const [config, setConfig] = useState({
    kb_url: "",
    username: "",
    password: "",
    kb_name: ""
  });
  const [testing, setTesting] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState(null);
  
  // Push to Agiloft state
  const [pushing, setPushing] = useState(false);
  const [pushResult, setPushResult] = useState(null);
  const [clauseSource, setClauseSource] = useState("database"); // database or acquisition
  
  // Agiloft contracts state
  const [loadingContracts, setLoadingContracts] = useState(false);
  const [agiloftContracts, setAgiloftContracts] = useState([]);
  const [selectedContract, setSelectedContract] = useState(null);
  const [analyzingContract, setAnalyzingContract] = useState(false);
  const [contractAnalysis, setContractAnalysis] = useState(null);
  
  // Contract search filters
  const [contractSearch, setContractSearch] = useState("");
  const [contractTypeFilter, setContractTypeFilter] = useState("");
  const [contractIdFilter, setContractIdFilter] = useState("");

  // Clause comparison state
  const [comparing, setComparing] = useState(false);
  const [comparisonResult, setComparisonResult] = useState(null);
  const [comparisonClauseType, setComparisonClauseType] = useState("");
  const [comparisonSource, setComparisonSource] = useState("acquisition_gov");
  const [selectedMissingClauses, setSelectedMissingClauses] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [fetchFresh, setFetchFresh] = useState(false);

  const handleConfigChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const testConnection = async () => {
    if (!config.kb_url || !config.username || !config.password || !config.kb_name) {
      toast.error("Please fill in all required fields including KB Name");
      return;
    }

    setTesting(true);
    setConnectionStatus(null);

    try {
      const response = await fetch(`${API}/agiloft/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(config)
      });

      // Clone the response before reading to prevent "body stream already read" error
      const responseClone = response.clone();
      
      let result;
      try {
        result = await response.json();
      } catch (parseError) {
        // If JSON parsing fails, try to get text
        const text = await responseClone.text();
        result = { 
          success: false, 
          message: text || `HTTP Error ${response.status}`,
          detail: text
        };
      }
      
      // Handle HTTP error status codes (like 401, 503, etc.)
      if (!response.ok) {
        const errorMessage = result.detail || result.message || `HTTP Error ${response.status}`;
        setConnectionStatus({ success: false, message: errorMessage });
        toast.error(errorMessage);
        return;
      }
      
      setConnectionStatus(result);
      
      if (result.success) {
        toast.success("Connection successful!");
      } else {
        toast.error(result.message || "Connection failed");
      }
    } catch (error) {
      console.error("Agiloft connection error:", error);
      setConnectionStatus({ success: false, message: `Connection error: ${error.message}` });
      toast.error(`Connection test failed: ${error.message}`);
    } finally {
      setTesting(false);
    }
  };

  const pushClausesToAgiloft = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    setPushing(true);
    setPushResult(null);

    try {
      const response = await fetch(`${API}/agiloft/push-clauses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          source: clauseSource
        })
      });

      const result = await response.json();
      setPushResult(result);
      
      if (result.success) {
        toast.success(`Pushed ${result.pushed_count} clauses to Agiloft!`);
      } else {
        toast.error(result.message || "Push failed");
      }
    } catch (error) {
      setPushResult({ success: false, message: error.message });
      toast.error("Push failed");
    } finally {
      setPushing(false);
    }
  };

  const fetchAgiloftContracts = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    setLoadingContracts(true);
    setSelectedContract(null);
    setContractAnalysis(null);

    try {
      const response = await fetch(`${API}/agiloft/contracts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ config, limit: 50 })
      });

      const result = await response.json();
      
      if (!response.ok) {
        const errorMessage = result.detail || result.message || `HTTP Error ${response.status}`;
        toast.error(errorMessage);
        return;
      }
      
      if (result.success) {
        setAgiloftContracts(result.contracts || []);
        if (result.contracts?.length > 0) {
          toast.success(`Loaded ${result.contracts.length} contracts from Agiloft`);
        } else {
          toast.info("No contracts found in Agiloft");
        }
      } else {
        toast.error(result.message || "Failed to load contracts");
      }
    } catch (error) {
      toast.error(`Failed to load contracts: ${error.message}`);
    } finally {
      setLoadingContracts(false);
    }
  };

  const searchContracts = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    setLoadingContracts(true);
    setSelectedContract(null);
    setContractAnalysis(null);

    try {
      const searchParams = {
        config,
        limit: 50
      };
      
      // Add search filters
      if (contractSearch.trim()) {
        searchParams.search_query = contractSearch.trim();
      }
      if (contractTypeFilter.trim()) {
        searchParams.contract_type = contractTypeFilter.trim();
      }
      if (contractIdFilter.trim()) {
        searchParams.contract_id = contractIdFilter.trim();
      }

      const response = await fetch(`${API}/agiloft/contracts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(searchParams)
      });

      const result = await response.json();
      
      if (!response.ok) {
        const errorMessage = result.detail || result.message || `HTTP Error ${response.status}`;
        toast.error(errorMessage);
        return;
      }
      
      if (result.success) {
        setAgiloftContracts(result.contracts || []);
        if (result.contracts?.length > 0) {
          toast.success(`Found ${result.contracts.length} contracts`);
        } else {
          toast.info("No contracts match your search criteria");
        }
      } else {
        toast.error(result.message || "Search failed");
      }
    } catch (error) {
      toast.error(`Search failed: ${error.message}`);
    } finally {
      setLoadingContracts(false);
    }
  };

  const analyzeContract = async (contract) => {
    setSelectedContract(contract);
    setAnalyzingContract(true);
    setContractAnalysis(null);

    try {
      const response = await fetch(`${API}/agiloft/analyze-contract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          contract_id: contract.id,
          contract_clauses: contract.clauses || [],
          contract_type: contract.type || "Fixed-Price",
          contract_value: contract.value || 0
        })
      });

      const result = await response.json();
      setContractAnalysis(result);
      
      if (result.success) {
        toast.success("Analysis complete");
      }
    } catch (error) {
      toast.error("Analysis failed");
    } finally {
      setAnalyzingContract(false);
    }
  };

  const updateAgiloftContract = async () => {
    if (!contractAnalysis || !selectedContract) return;

    try {
      const response = await fetch(`${API}/agiloft/update-contract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          contract_id: selectedContract.id,
          updates: {
            missing_clauses: contractAnalysis.missing_clauses,
            flowdown_clauses: contractAnalysis.required_flowdown
          }
        })
      });

      const result = await response.json();
      
      if (result.success) {
        toast.success("Contract updated in Agiloft!");
        fetchAgiloftContracts();
      } else {
        toast.error(result.message || "Update failed");
      }
    } catch (error) {
      toast.error("Update failed");
    }
  };

  // Compare clauses between source (acquisition.gov or local DB) and Agiloft
  const compareClausesWithAgiloft = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    setComparing(true);
    setComparisonResult(null);
    setSelectedMissingClauses([]);

    try {
      // Use the new comparison endpoint
      const response = await fetch(`${API}/comparison/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          clause_type: comparisonClauseType || null,
          source: comparisonSource || "acquisition_gov"
        })
      });

      const result = await response.json();
      
      if (!response.ok) {
        toast.error(result.detail || "Comparison failed");
        return;
      }
      
      setComparisonResult(result);
      
      if (result.success) {
        toast.success(`Comparison complete! ${result.matched_count} clauses matched, ${result.missing_in_agiloft_count} missing in Agiloft`);
      } else {
        toast.error(result.message || "Comparison failed");
      }
    } catch (error) {
      toast.error(`Comparison failed: ${error.message}`);
    } finally {
      setComparing(false);
    }
  };

  // Upload selected missing clauses to Agiloft
  const uploadMissingClausesToAgiloft = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    if (selectedMissingClauses.length === 0) {
      toast.error("Please select clauses to upload");
      return;
    }

    setUploading(true);

    try {
      // Use the new upload endpoint
      const response = await fetch(`${API}/comparison/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          clause_numbers: selectedMissingClauses,
          fetch_text: fetchFresh
        })
      });

      const result = await response.json();
      
      if (!response.ok) {
        toast.error(result.detail || "Upload failed");
        return;
      }
      
      if (result.success || result.uploaded_count > 0) {
        toast.success(`Uploaded ${result.uploaded_count} of ${result.total_requested} clauses`);
        // Refresh comparison after upload
        compareClausesWithAgiloft();
      } else {
        toast.error(result.message || "Upload failed");
      }
    } catch (error) {
      toast.error(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  // Toggle clause selection for upload
  const toggleClauseSelection = (clauseNumber) => {
    setSelectedMissingClauses(prev => 
      prev.includes(clauseNumber)
        ? prev.filter(n => n !== clauseNumber)
        : [...prev, clauseNumber]
    );
  };

  // Select all missing clauses
  const selectAllMissingClauses = () => {
    if (comparisonResult?.missing_in_agiloft) {
      setSelectedMissingClauses(comparisonResult.missing_in_agiloft.map(c => c.number));
    }
  };

  // Clear all selections
  const clearAllSelections = () => {
    setSelectedMissingClauses([]);
  };

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
            Agiloft Integration
          </h1>
          <p className="text-slate-600">
            Push clause data to Agiloft and analyze Agiloft contracts for compliance
          </p>
        </div>

        {/* Connection Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 mb-8">
          <div className="flex items-center gap-3 mb-6">
            <Settings className="w-5 h-5 text-teal-600" />
            <h2 className="font-heading font-bold text-lg text-navy-900">Connection Settings</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <div>
              <Label htmlFor="kb_url">Agiloft Instance URL</Label>
              <Input
                id="kb_url"
                placeholder="https://yourinstance.saas.agiloft.com"
                value={config.kb_url}
                onChange={(e) => handleConfigChange("kb_url", e.target.value)}
                data-testid="kb-url-input"
              />
              <p className="text-xs text-slate-500 mt-1">Base URL only (e.g., https://elitebcopartnerkb.saas.agiloft.com)</p>
            </div>
            <div>
              <Label htmlFor="kb_name">Knowledge Base Name</Label>
              <Input
                id="kb_name"
                placeholder="YourKBName"
                value={config.kb_name}
                onChange={(e) => handleConfigChange("kb_name", e.target.value)}
              />
              <p className="text-xs text-slate-500 mt-1">Required - your KB identifier</p>
            </div>
            <div>
              <Label htmlFor="username">Username (login)</Label>
              <Input
                id="username"
                placeholder="api_user"
                value={config.username}
                onChange={(e) => handleConfigChange("username", e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={config.password}
                onChange={(e) => handleConfigChange("password", e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <Button
              onClick={testConnection}
              disabled={testing}
              variant="outline"
              data-testid="test-connection-btn"
            >
              {testing ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Link2 className="w-4 h-4 mr-2" />
              )}
              Test Connection
            </Button>

            {connectionStatus && (
              <div className={`flex items-start gap-2 max-w-xl ${
                connectionStatus.success ? "text-green-600" : "text-red-600"
              }`}>
                {connectionStatus.success ? (
                  <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                )}
                <span className="text-sm">
                  {connectionStatus.message || connectionStatus.detail || 
                   (connectionStatus.success ? "Connected successfully" : "Connection failed")}
                  {connectionStatus.token_preview && (
                    <span className="block text-xs text-slate-500 mt-1">
                      Token: {connectionStatus.token_preview}
                    </span>
                  )}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Tabs for different functions */}
        <Tabs defaultValue="compare" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 lg:w-auto lg:inline-grid">
            <TabsTrigger value="compare" className="gap-2">
              <RefreshCw className="w-4 h-4" />
              Compare Clauses
            </TabsTrigger>
            <TabsTrigger value="push" className="gap-2">
              <Upload className="w-4 h-4" />
              Push Clauses
            </TabsTrigger>
            <TabsTrigger value="analyze" className="gap-2">
              <FileText className="w-4 h-4" />
              Analyze Contracts
            </TabsTrigger>
          </TabsList>

          {/* Compare Clauses Tab */}
          <TabsContent value="compare">
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h3 className="font-heading font-bold text-lg text-navy-900 mb-2">
                Compare FAR/DFARS Clauses with Agiloft KB
              </h3>
              <p className="text-slate-600 mb-6">
                Compare clauses from acquisition.gov (FAR index) with your Agiloft Knowledge Base. Identify missing clauses and upload them directly.
              </p>

              <div className="space-y-4">
                {/* Filter options */}
                <div className="flex items-end gap-4 flex-wrap">
                  <div>
                    <Label>Source</Label>
                    <Select value={comparisonSource || "acquisition_gov"} onValueChange={(val) => setComparisonSource(val)}>
                      <SelectTrigger className="w-48" data-testid="comparison-source">
                        <SelectValue placeholder="acquisition.gov" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="acquisition_gov">acquisition.gov (Live)</SelectItem>
                        <SelectItem value="local_db">Local Database</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <Label>Clause Type Filter</Label>
                    <Select value={comparisonClauseType || "all"} onValueChange={(val) => setComparisonClauseType(val === "all" ? "" : val)}>
                      <SelectTrigger className="w-40" data-testid="comparison-type-filter">
                        <SelectValue placeholder="All Types" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Types</SelectItem>
                        <SelectItem value="FAR">FAR</SelectItem>
                        <SelectItem value="DFARS">DFARS</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <Button
                    onClick={compareClausesWithAgiloft}
                    disabled={comparing || !connectionStatus?.success}
                    className="bg-teal-600 hover:bg-teal-700"
                    data-testid="compare-clauses-btn"
                  >
                    {comparing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Comparing...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Compare Clauses
                      </>
                    )}
                  </Button>
                </div>

                {/* Comparison Results */}
                {comparisonResult && (
                  <div className="space-y-6 mt-6">
                    {/* Summary Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center p-4 bg-blue-50 rounded-lg border border-blue-100">
                        <div className="text-2xl font-bold text-blue-600">{comparisonResult.total_source_clauses || comparisonResult.total_local_clauses}</div>
                        <div className="text-xs text-slate-500">{comparisonResult.source || "Source"} Clauses</div>
                      </div>
                      <div className="text-center p-4 bg-purple-50 rounded-lg border border-purple-100">
                        <div className="text-2xl font-bold text-purple-600">{comparisonResult.total_agiloft_clauses}</div>
                        <div className="text-xs text-slate-500">Agiloft Clauses</div>
                      </div>
                      <div className="text-center p-4 bg-amber-50 rounded-lg border border-amber-100">
                        <div className="text-2xl font-bold text-amber-600">{comparisonResult.missing_in_agiloft_count}</div>
                        <div className="text-xs text-slate-500">Missing in Agiloft</div>
                      </div>
                      <div className="text-center p-4 bg-green-50 rounded-lg border border-green-100">
                        <div className="text-2xl font-bold text-green-600">{comparisonResult.matched_count}</div>
                        <div className="text-xs text-slate-500">Matched</div>
                      </div>
                    </div>

                    {/* Missing in Agiloft - with selection */}
                    {comparisonResult.missing_in_agiloft?.length > 0 && (
                      <div className="bg-amber-50 rounded-lg p-4 border border-amber-200">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5 text-amber-600" />
                            <span className="font-medium text-amber-800">
                              Clauses Missing in Agiloft ({comparisonResult.missing_in_agiloft.length})
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={selectAllMissingClauses}
                              className="text-amber-700 hover:bg-amber-100"
                            >
                              Select All
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={clearAllSelections}
                              className="text-amber-700 hover:bg-amber-100"
                            >
                              Clear
                            </Button>
                          </div>
                        </div>
                        
                        <div className="max-h-64 overflow-y-auto space-y-2">
                          {comparisonResult.missing_in_agiloft.map(clause => (
                            <div 
                              key={clause.number}
                              className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
                                selectedMissingClauses.includes(clause.number) 
                                  ? "bg-amber-100 border border-amber-300" 
                                  : "bg-white/50 hover:bg-amber-100/50"
                              }`}
                              onClick={() => toggleClauseSelection(clause.number)}
                              data-testid={`missing-clause-${clause.number}`}
                            >
                              <input 
                                type="checkbox"
                                checked={selectedMissingClauses.includes(clause.number)}
                                onChange={() => toggleClauseSelection(clause.number)}
                                className="w-4 h-4 text-amber-600 rounded"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-medium text-amber-800">{clause.number}</span>
                                  <Badge className={
                                    clause.type === "FAR" 
                                      ? "bg-blue-100 text-blue-700" 
                                      : "bg-purple-100 text-purple-700"
                                  }>
                                    {clause.type}
                                  </Badge>
                                  {clause.flowdown_required && (
                                    <Badge className="bg-red-100 text-red-700 text-xs">Flowdown</Badge>
                                  )}
                                </div>
                                <p className="text-sm text-slate-600 truncate">{clause.title}</p>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Upload Options */}
                        <div className="mt-4 pt-4 border-t border-amber-200">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <input 
                                type="checkbox"
                                id="fetchFresh"
                                checked={fetchFresh}
                                onChange={(e) => setFetchFresh(e.target.checked)}
                                className="w-4 h-4 text-teal-600 rounded"
                              />
                              <Label htmlFor="fetchFresh" className="text-sm text-slate-700 cursor-pointer">
                                Fetch fresh data from acquisition.gov
                              </Label>
                            </div>
                            <span className="text-sm text-amber-700">
                              {selectedMissingClauses.length} selected
                            </span>
                          </div>
                          
                          <Button
                            onClick={uploadMissingClausesToAgiloft}
                            disabled={uploading || selectedMissingClauses.length === 0 || !connectionStatus?.success}
                            className="w-full bg-amber-600 hover:bg-amber-700 text-white"
                            data-testid="upload-missing-btn"
                          >
                            {uploading ? (
                              <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                Uploading...
                              </>
                            ) : (
                              <>
                                <Upload className="w-4 h-4 mr-2" />
                                Upload {selectedMissingClauses.length} Clauses to Agiloft
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Matched Clauses */}
                    {comparisonResult.matched_clauses?.length > 0 && (
                      <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                        <div className="flex items-center gap-2 mb-3">
                          <Check className="w-5 h-5 text-green-600" />
                          <span className="font-medium text-green-800">
                            Matched Clauses ({comparisonResult.matched_count})
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                          {comparisonResult.matched_clauses.slice(0, 20).map(clause => (
                            <Badge 
                              key={clause.number} 
                              variant="outline" 
                              className="border-green-300 text-green-700"
                            >
                              {clause.number}
                            </Badge>
                          ))}
                          {comparisonResult.matched_clauses.length > 20 && (
                            <Badge variant="outline" className="border-slate-300">
                              +{comparisonResult.matched_clauses.length - 20} more
                            </Badge>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Missing in Local DB */}
                    {comparisonResult.missing_in_local?.length > 0 && (
                      <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                        <div className="flex items-center gap-2 mb-3">
                          <Database className="w-5 h-5 text-blue-600" />
                          <span className="font-medium text-blue-800">
                            In Agiloft but not in Local DB ({comparisonResult.missing_in_local_count})
                          </span>
                        </div>
                        <div className="max-h-32 overflow-y-auto space-y-1">
                          {comparisonResult.missing_in_local.slice(0, 10).map((clause, idx) => (
                            <div key={idx} className="text-sm text-blue-700 flex items-center gap-2">
                              <span>{clause.clause_title || clause.agiloft_id}</span>
                              {clause.normalized && (
                                <span className="text-xs bg-blue-100 px-1 rounded">{clause.normalized}</span>
                              )}
                              {clause.note && (
                                <span className="text-xs text-blue-500 italic">({clause.note})</span>
                              )}
                            </div>
                          ))}
                          {comparisonResult.missing_in_local.length > 10 && (
                            <div className="text-sm text-slate-500">
                              +{comparisonResult.missing_in_local.length - 10} more
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Debug Info */}
                    {comparisonResult.debug && (
                      <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                        <div className="flex items-center gap-2 mb-3">
                          <Settings className="w-4 h-4 text-slate-500" />
                          <span className="font-medium text-slate-700 text-sm">Comparison Debug Info</span>
                        </div>
                        <div className="grid grid-cols-2 gap-4 text-xs">
                          <div>
                            <p className="text-slate-500">Local normalized: {comparisonResult.debug.local_normalized_count}</p>
                            <p className="text-slate-500">Agiloft normalized: {comparisonResult.debug.agiloft_normalized_count}</p>
                            <p className="text-slate-500">Unmatched pattern: {comparisonResult.debug.agiloft_unmatched_pattern_count}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">Sample local: {comparisonResult.debug.sample_local_numbers?.join(', ')}</p>
                            <p className="text-slate-500">Sample Agiloft: {comparisonResult.debug.sample_agiloft_numbers?.join(', ')}</p>
                          </div>
                        </div>
                        <p className="text-xs text-slate-400 mt-2">{comparisonResult.debug.normalization_note}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          {/* Push Clauses Tab */}
          <TabsContent value="push">
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h3 className="font-heading font-bold text-lg text-navy-900 mb-4">
                Push Clauses to Agiloft Knowledge Base
              </h3>
              <p className="text-slate-600 mb-6">
                Update your Agiloft clause library with FAR/DFARS clauses from our database or live from acquisition.gov
              </p>

              <div className="space-y-4">
                <div>
                  <Label>Clause Source</Label>
                  <Select value={clauseSource} onValueChange={setClauseSource}>
                    <SelectTrigger className="w-full md:w-64" data-testid="source-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="database">Our Clause Database</SelectItem>
                      <SelectItem value="acquisition">Live from acquisition.gov</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-slate-500 mt-1">
                    {clauseSource === "database" 
                      ? "Push all clauses currently in our database" 
                      : "Fetch fresh data from acquisition.gov and push to Agiloft"
                    }
                  </p>
                </div>

                <Button
                  onClick={pushClausesToAgiloft}
                  disabled={pushing || !connectionStatus?.success}
                  className="bg-teal-600 hover:bg-teal-700"
                  data-testid="push-btn"
                >
                  {pushing ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Pushing...
                    </>
                  ) : (
                    <>
                      <ArrowUpRight className="w-4 h-4 mr-2" />
                      Push Clauses to Agiloft
                    </>
                  )}
                </Button>

                {pushResult && (
                  <div className={`p-4 rounded-lg ${
                    pushResult.success 
                      ? "bg-green-50 border border-green-200" 
                      : "bg-red-50 border border-red-200"
                  }`}>
                    <div className="flex items-center gap-2 mb-2">
                      {pushResult.success ? (
                        <CheckCircle className="w-5 h-5 text-green-600" />
                      ) : (
                        <AlertCircle className="w-5 h-5 text-red-600" />
                      )}
                      <span className={pushResult.success ? "text-green-700 font-medium" : "text-red-700"}>
                        {pushResult.message}
                      </span>
                    </div>
                    {pushResult.success && (
                      <div className="text-sm text-green-600">
                        <p>Created: {pushResult.created_count || 0} clauses</p>
                        <p>Updated: {pushResult.updated_count || 0} clauses</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          {/* Analyze Contracts Tab */}
          <TabsContent value="analyze">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Contracts List */}
              <div className="bg-white rounded-xl border border-slate-200">
                <div className="p-6 border-b border-slate-100">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-heading font-bold text-lg text-navy-900">
                      Agiloft Contracts
                    </h3>
                    <Button
                      onClick={fetchAgiloftContracts}
                      disabled={loadingContracts || !connectionStatus?.success}
                      variant="outline"
                      size="sm"
                      data-testid="fetch-contracts-btn"
                    >
                      {loadingContracts ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <RefreshCw className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                  
                  {/* Search Filters */}
                  <div className="space-y-3">
                    <div>
                      <Label htmlFor="contractSearch" className="text-xs">Search by Contract Title</Label>
                      <Input
                        id="contractSearch"
                        placeholder="Search contracts..."
                        value={contractSearch}
                        onChange={(e) => setContractSearch(e.target.value)}
                        className="h-9"
                        data-testid="contract-search-input"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label htmlFor="contractTypeFilter" className="text-xs">Contract Type</Label>
                        <Input
                          id="contractTypeFilter"
                          placeholder="e.g., Services Agreement"
                          value={contractTypeFilter}
                          onChange={(e) => setContractTypeFilter(e.target.value)}
                          className="h-9"
                          data-testid="contract-type-filter"
                        />
                      </div>
                      <div>
                        <Label htmlFor="contractIdFilter" className="text-xs">Contract ID</Label>
                        <Input
                          id="contractIdFilter"
                          placeholder="e.g., 690"
                          value={contractIdFilter}
                          onChange={(e) => setContractIdFilter(e.target.value)}
                          className="h-9"
                          data-testid="contract-id-filter"
                        />
                      </div>
                    </div>
                    <Button
                      onClick={searchContracts}
                      disabled={loadingContracts || !connectionStatus?.success}
                      variant="default"
                      size="sm"
                      className="w-full bg-teal-600 hover:bg-teal-700"
                      data-testid="search-contracts-btn"
                    >
                      {loadingContracts ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Search className="w-4 h-4 mr-2" />
                      )}
                      Search Contracts
                    </Button>
                  </div>
                </div>

                <div className="max-h-96 overflow-y-auto">
                  {agiloftContracts.length === 0 ? (
                    <div className="p-8 text-center">
                      <Database className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                      <p className="text-slate-500">
                        {connectionStatus?.success 
                          ? "Search for contracts in Agiloft"
                          : "Connect to Agiloft to view contracts"
                        }
                      </p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {agiloftContracts.map((contract) => (
                        <div
                          key={contract.id}
                          className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors ${
                            selectedContract?.id === contract.id ? "bg-teal-50 border-l-4 border-teal-500" : ""
                          }`}
                          onClick={() => setSelectedContract(contract)}
                          data-testid={`contract-${contract.id}`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-navy-900 truncate">
                                {contract.contract_title || contract.name || `Contract #${contract.id}`}
                              </p>
                              <p className="text-sm text-slate-500">
                                ID: {contract.id} • {contract.contract_type || contract.type || "Unknown Type"}
                              </p>
                              {contract.company_name && (
                                <p className="text-xs text-slate-400">{contract.company_name}</p>
                              )}
                              {contract.status && (
                                <p className="text-xs text-slate-400 mt-1">Status: {contract.status}</p>
                              )}
                            </div>
                            <Badge className={
                              contract.status === "Active" || contract.status === "Executed"
                                ? "bg-green-100 text-green-700"
                                : contract.status === "Draft"
                                ? "bg-slate-100 text-slate-700"
                                : "bg-amber-100 text-amber-700"
                            }>
                              {contract.status || "N/A"}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                
                {agiloftContracts.length > 0 && (
                  <div className="p-4 border-t border-slate-100 text-sm text-slate-500">
                    Showing {agiloftContracts.length} contracts
                  </div>
                )}
              </div>

              {/* Contract Details & Analysis */}
              <div className="bg-white rounded-xl border border-slate-200">
                <div className="p-6 border-b border-slate-100">
                  <h3 className="font-heading font-bold text-lg text-navy-900">
                    {selectedContract ? "Contract Details & Analysis" : "Select a Contract"}
                  </h3>
                </div>

                <div className="p-6">
                  {!selectedContract ? (
                    <div className="text-center py-8">
                      <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                      <p className="text-slate-500">Select a contract from the list to view details and analyze</p>
                    </div>
                  ) : analyzingContract ? (
                    <div className="text-center py-8">
                      <Loader2 className="w-8 h-8 animate-spin text-teal-600 mx-auto mb-4" />
                      <p className="text-slate-500">Analyzing contract...</p>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {/* Contract Info */}
                      <div className="bg-slate-50 rounded-lg p-4">
                        <h4 className="font-medium text-navy-900 mb-3">
                          {selectedContract.contract_title || selectedContract.name}
                        </h4>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div>
                            <span className="text-slate-500">ID:</span>{" "}
                            <span className="font-medium">{selectedContract.id}</span>
                          </div>
                          <div>
                            <span className="text-slate-500">Type:</span>{" "}
                            <span className="font-medium">{selectedContract.contract_type || selectedContract.type || "N/A"}</span>
                          </div>
                          {selectedContract.company_name && (
                            <div className="col-span-2">
                              <span className="text-slate-500">Company:</span>{" "}
                              <span className="font-medium">{selectedContract.company_name}</span>
                            </div>
                          )}
                          <div>
                            <span className="text-slate-500">Status:</span>{" "}
                            <span className="font-medium">{selectedContract.status || "N/A"}</span>
                          </div>
                          {selectedContract.value > 0 && (
                            <div>
                              <span className="text-slate-500">Value:</span>{" "}
                              <span className="font-medium">${selectedContract.value.toLocaleString()}</span>
                            </div>
                          )}
                        </div>
                        
                        <Button
                          onClick={() => analyzeContract(selectedContract)}
                          disabled={analyzingContract}
                          className="w-full mt-4 bg-teal-600 hover:bg-teal-700"
                          data-testid="analyze-contract-btn"
                        >
                          {analyzingContract ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          ) : (
                            <Check className="w-4 h-4 mr-2" />
                          )}
                          Analyze for Compliance
                        </Button>
                      </div>

                      {/* Analysis Results */}
                      {contractAnalysis && (
                        <div className="space-y-4">
                          {/* Summary Stats */}
                          <div className="grid grid-cols-3 gap-3">
                            <div className="text-center p-3 bg-green-50 rounded-lg">
                              <div className="text-xl font-bold text-green-600">{contractAnalysis.correct_clauses?.length || 0}</div>
                              <div className="text-xs text-slate-500">Correct</div>
                            </div>
                            <div className="text-center p-3 bg-amber-50 rounded-lg">
                              <div className="text-xl font-bold text-amber-600">{contractAnalysis.missing_clauses?.length || 0}</div>
                              <div className="text-xs text-slate-500">Missing</div>
                            </div>
                            <div className="text-center p-3 bg-red-50 rounded-lg">
                              <div className="text-xl font-bold text-red-600">{contractAnalysis.needs_update?.length || 0}</div>
                              <div className="text-xs text-slate-500">Need Update</div>
                            </div>
                          </div>

                          {/* Missing Clauses */}
                          {contractAnalysis.missing_clauses?.length > 0 && (
                            <div className="bg-amber-50 rounded-lg p-4 border border-amber-200">
                              <div className="flex items-center gap-2 mb-2">
                                <AlertTriangle className="w-5 h-5 text-amber-600" />
                                <span className="font-medium text-amber-800">Missing Clauses</span>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {contractAnalysis.missing_clauses.map(clause => (
                                  <Badge key={clause} variant="outline" className="border-amber-300 text-amber-700">
                                    {clause}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Correct Clauses */}
                          {contractAnalysis.correct_clauses?.length > 0 && (
                            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                              <div className="flex items-center gap-2 mb-2">
                                <Check className="w-5 h-5 text-green-600" />
                                <span className="font-medium text-green-800">Correct Clauses</span>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {contractAnalysis.correct_clauses.slice(0, 10).map(clause => (
                                  <Badge key={clause} variant="outline" className="border-green-300 text-green-700">
                                    {clause}
                                  </Badge>
                                ))}
                                {contractAnalysis.correct_clauses.length > 10 && (
                                  <Badge variant="outline">+{contractAnalysis.correct_clauses.length - 10} more</Badge>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Update Button */}
                          {(contractAnalysis.missing_clauses?.length > 0 || contractAnalysis.needs_update?.length > 0) && (
                            <Button
                              onClick={updateAgiloftContract}
                              className="w-full bg-teal-600 hover:bg-teal-700"
                              data-testid="update-contract-btn"
                            >
                              <ArrowUpRight className="w-4 h-4 mr-2" />
                              Update Contract in Agiloft
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
