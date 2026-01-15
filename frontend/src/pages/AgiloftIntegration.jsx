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
        <Tabs defaultValue="push" className="space-y-6">
          <TabsList className="grid w-full grid-cols-2 lg:w-auto lg:inline-grid">
            <TabsTrigger value="push" className="gap-2">
              <Upload className="w-4 h-4" />
              Push Clauses to Agiloft
            </TabsTrigger>
            <TabsTrigger value="analyze" className="gap-2">
              <FileText className="w-4 h-4" />
              Analyze Agiloft Contracts
            </TabsTrigger>
          </TabsList>

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
                      <Button
                        onClick={updateAgiloftContract}
                        className="w-full bg-teal-600 hover:bg-teal-700"
                        disabled={!contractAnalysis.missing_clauses?.length && !contractAnalysis.needs_update?.length}
                        data-testid="update-contract-btn"
                      >
                        <ArrowUpRight className="w-4 h-4 mr-2" />
                        Update Contract in Agiloft
                      </Button>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                      <p className="text-slate-500">
                        Select a contract to analyze for compliance
                      </p>
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
