import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Database, RefreshCw, CheckCircle, 
  AlertCircle, Loader2, Settings, Link2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function AgiloftIntegration({ user }) {
  const navigate = useNavigate();
  const [config, setConfig] = useState({
    kb_url: "",
    username: "",
    password: "",
    kb_name: "Default"
  });
  const [tableName, setTableName] = useState("Clauses");
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  const handleConfigChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const testConnection = async () => {
    if (!config.kb_url || !config.username || !config.password) {
      toast.error("Please fill in all required fields");
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

      const result = await response.json();
      setConnectionStatus(result);
      
      if (result.success) {
        toast.success("Connection successful!");
      } else {
        toast.error(result.message || "Connection failed");
      }
    } catch (error) {
      setConnectionStatus({ success: false, message: error.message });
      toast.error("Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  const syncClauses = async () => {
    if (!connectionStatus?.success) {
      toast.error("Please test connection first");
      return;
    }

    setSyncing(true);
    setSyncResult(null);

    try {
      const response = await fetch(`${API}/agiloft/sync-clauses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          config,
          table_name: tableName,
          field_mapping: {}
        })
      });

      const result = await response.json();
      setSyncResult(result);
      
      if (result.success) {
        toast.success(`Synced ${result.synced_count} clauses!`);
      } else {
        toast.error(result.message || "Sync failed");
      }
    } catch (error) {
      setSyncResult({ success: false, message: error.message });
      toast.error("Sync failed");
    } finally {
      setSyncing(false);
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
      <main className="max-w-4xl mx-auto px-6 md:px-12 py-8">
        <div className="mb-8">
          <h1 className="font-heading font-bold text-3xl text-navy-900 mb-2">
            Agiloft Integration
          </h1>
          <p className="text-slate-600">
            Connect to your Agiloft knowledge base to sync clause data
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Configuration */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center gap-3 mb-6">
              <Settings className="w-5 h-5 text-teal-600" />
              <h2 className="font-heading font-bold text-lg text-navy-900">Connection Settings</h2>
            </div>

            <div className="space-y-4">
              <div>
                <Label htmlFor="kb_url">Knowledge Base URL</Label>
                <Input
                  id="kb_url"
                  placeholder="https://yourcompany.agiloft.com/ewws"
                  value={config.kb_url}
                  onChange={(e) => handleConfigChange("kb_url", e.target.value)}
                  data-testid="kb-url-input"
                />
                <p className="text-xs text-slate-500 mt-1">
                  The base URL of your Agiloft instance (ending with /ewws)
                </p>
              </div>

              <div>
                <Label htmlFor="kb_name">Knowledge Base Name</Label>
                <Input
                  id="kb_name"
                  placeholder="Default"
                  value={config.kb_name}
                  onChange={(e) => handleConfigChange("kb_name", e.target.value)}
                  data-testid="kb-name-input"
                />
              </div>

              <div>
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  placeholder="api_user"
                  value={config.username}
                  onChange={(e) => handleConfigChange("username", e.target.value)}
                  data-testid="username-input"
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
                  data-testid="password-input"
                />
              </div>

              <Button
                onClick={testConnection}
                disabled={testing}
                className="w-full"
                variant="outline"
                data-testid="test-connection-btn"
              >
                {testing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Testing...
                  </>
                ) : (
                  <>
                    <Link2 className="w-4 h-4 mr-2" />
                    Test Connection
                  </>
                )}
              </Button>

              {connectionStatus && (
                <div className={`p-4 rounded-lg ${
                  connectionStatus.success 
                    ? "bg-green-50 border border-green-200" 
                    : "bg-red-50 border border-red-200"
                }`}>
                  <div className="flex items-center gap-2">
                    {connectionStatus.success ? (
                      <CheckCircle className="w-5 h-5 text-green-600" />
                    ) : (
                      <AlertCircle className="w-5 h-5 text-red-600" />
                    )}
                    <span className={connectionStatus.success ? "text-green-700" : "text-red-700"}>
                      {connectionStatus.message}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Sync Options */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center gap-3 mb-6">
              <Database className="w-5 h-5 text-teal-600" />
              <h2 className="font-heading font-bold text-lg text-navy-900">Sync Clauses</h2>
            </div>

            <div className="space-y-4">
              <div>
                <Label htmlFor="table_name">Table Name</Label>
                <Input
                  id="table_name"
                  placeholder="Clauses"
                  value={tableName}
                  onChange={(e) => setTableName(e.target.value)}
                  data-testid="table-name-input"
                />
                <p className="text-xs text-slate-500 mt-1">
                  The name of the table in Agiloft containing clause data
                </p>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <h3 className="font-medium text-navy-900 mb-2">Expected Fields</h3>
                <p className="text-sm text-slate-600 mb-2">
                  Your Agiloft table should have these fields (or similar):
                </p>
                <ul className="text-sm text-slate-600 space-y-1">
                  <li>• <code className="bg-slate-200 px-1 rounded">clause_number</code> - Clause identifier (e.g., 52.212-4)</li>
                  <li>• <code className="bg-slate-200 px-1 rounded">clause_title</code> - Clause name</li>
                  <li>• <code className="bg-slate-200 px-1 rounded">clause_type</code> - FAR/DFARS/Custom</li>
                  <li>• <code className="bg-slate-200 px-1 rounded">clause_text</code> - Full clause text</li>
                  <li>• <code className="bg-slate-200 px-1 rounded">flowdown_required</code> - Boolean</li>
                </ul>
              </div>

              <Button
                onClick={syncClauses}
                disabled={syncing || !connectionStatus?.success}
                className="w-full bg-teal-600 hover:bg-teal-700"
                data-testid="sync-btn"
              >
                {syncing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Syncing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Sync Clauses from Agiloft
                  </>
                )}
              </Button>

              {syncResult && (
                <div className={`p-4 rounded-lg ${
                  syncResult.success 
                    ? "bg-green-50 border border-green-200" 
                    : "bg-red-50 border border-red-200"
                }`}>
                  <div className="flex items-center gap-2">
                    {syncResult.success ? (
                      <CheckCircle className="w-5 h-5 text-green-600" />
                    ) : (
                      <AlertCircle className="w-5 h-5 text-red-600" />
                    )}
                    <span className={syncResult.success ? "text-green-700" : "text-red-700"}>
                      {syncResult.message}
                    </span>
                  </div>
                  {syncResult.synced_count > 0 && (
                    <p className="text-sm text-green-600 mt-2">
                      Successfully synced {syncResult.synced_count} clauses
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Info Section */}
        <div className="mt-8 bg-blue-50 rounded-xl border border-blue-200 p-6">
          <h3 className="font-heading font-bold text-blue-800 mb-3">About Agiloft Integration</h3>
          <div className="text-sm text-blue-700 space-y-2">
            <p>
              Agiloft is a contract lifecycle management platform. This integration allows you to:
            </p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Sync clause libraries from your Agiloft knowledge base</li>
              <li>Keep your clause database up-to-date with your CLM system</li>
              <li>Import custom clauses alongside standard FAR/DFARS clauses</li>
            </ul>
            <p className="mt-3">
              <strong>Setup Requirements:</strong>
            </p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Enable Web Services in Agiloft (Setup → System → Manage Web Services)</li>
              <li>Create an API user with REST access permissions</li>
              <li>Ensure the user has read access to the Clauses table</li>
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
}
