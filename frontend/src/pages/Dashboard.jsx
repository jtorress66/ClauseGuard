import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  Search, FileText, Download, LogOut, Star, 
  Clock, Upload, ChevronRight, BarChart3, BookOpen, 
  Bell, Settings, Plus, Trash2, Database, ArrowRight, RefreshCw, Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function Dashboard({ user }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [contracts, setContracts] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [savedSearches, setSavedSearches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [contractsRes, favoritesRes, searchesRes] = await Promise.all([
        fetch(`${API}/contracts/`, { credentials: "include" }),
        fetch(`${API}/user/favorites`, { credentials: "include" }),
        fetch(`${API}/user/saved-searches`, { credentials: "include" })
      ]);

      if (contractsRes.ok) {
        const data = await contractsRes.json();
        setContracts(data.contracts || []);
      }
      if (favoritesRes.ok) {
        const data = await favoritesRes.json();
        setFavorites(data.favorites || []);
      }
      if (searchesRes.ok) {
        const data = await searchesRes.json();
        setSavedSearches(data.saved_searches || []);
      }
    } catch (error) {
      console.error("Error fetching dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery)}&ai=true`);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, {
        method: "POST",
        credentials: "include"
      });
      navigate("/");
    } catch (error) {
      console.error("Logout error:", error);
      navigate("/");
    }
  };

  const removeFavorite = async (clauseId) => {
    try {
      const response = await fetch(`${API}/user/favorites/${clauseId}`, {
        method: "DELETE",
        credentials: "include"
      });
      if (response.ok) {
        setFavorites(favorites.filter(f => f.clause_id !== clauseId));
        toast.success("Removed from favorites");
      }
    } catch (error) {
      toast.error("Failed to remove favorite");
    }
  };

  const deleteSavedSearch = async (searchId) => {
    try {
      const response = await fetch(`${API}/user/saved-searches/${searchId}`, {
        method: "DELETE",
        credentials: "include"
      });
      if (response.ok) {
        setSavedSearches(savedSearches.filter(s => s.search_id !== searchId));
        toast.success("Search deleted");
      }
    } catch (error) {
      toast.error("Failed to delete search");
    }
  };

  const syncAllClauses = async () => {
    setSyncing(true);
    toast.info("Syncing clauses from acquisition.gov...");
    
    try {
      // First sync clause index
      const indexRes = await fetch(`${API}/clauses/sync-from-acquisition-gov`, {
        method: "POST",
        credentials: "include"
      });
      
      if (indexRes.ok) {
        const indexData = await indexRes.json();
        toast.success(`Synced ${indexData.total_new} new clauses from index`);
      }
      
      // Then sync full text for clauses missing it
      const textRes = await fetch(`${API}/clauses/sync-full-text?limit=100`, {
        method: "POST",
        credentials: "include"
      });
      
      if (textRes.ok) {
        const textData = await textRes.json();
        if (textData.synced > 0) {
          toast.success(`Synced full text for ${textData.synced} clauses`);
        } else if (textData.total_checked === 0) {
          toast.info("All clauses already have full text");
        }
      }
    } catch (error) {
      console.error("Sync error:", error);
      toast.error("Failed to sync clauses");
    } finally {
      setSyncing(false);
    }
  };

  const quickActions = [
    { icon: Search, label: "AI Clause Search", desc: "Smart search", onClick: () => navigate("/search?ai=true"), color: "from-teal-500 to-emerald-500" },
    { icon: Upload, label: "Upload Contract", desc: "Analyze docs", onClick: () => navigate("/upload"), color: "from-slate-600 to-slate-700" },
    { icon: Download, label: "Flowdown Analysis", desc: "Check compliance", onClick: () => navigate("/flowdown"), color: "from-amber-500 to-orange-500" },
    { icon: FileText, label: "Compare Contracts", desc: "Side by side", onClick: () => navigate("/compare"), color: "from-violet-500 to-purple-500" },
    { icon: BarChart3, label: "Batch Export", desc: "Export clauses", onClick: () => navigate("/export"), color: "from-blue-500 to-indigo-500" },
    { icon: Database, label: "Agiloft Sync", desc: "Integration", onClick: () => navigate("/agiloft"), color: "from-slate-500 to-zinc-600" },
    { icon: RefreshCw, label: "Sync All Clauses", desc: "Fetch full text", onClick: syncAllClauses, color: "from-emerald-500 to-teal-600", loading: syncing }
  ];

  return (
    <div className="min-h-screen app-background-soft">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => navigate("/")}>
                <ClauseGuardLogo className="w-8 h-8" variant="light" />
                <span className="font-semibold text-xl text-slate-800 tracking-tight">ClauseGuard</span>
              </div>
              
              <form onSubmit={handleSearch} className="hidden md:flex">
                <div className="relative">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    type="text"
                    placeholder="Search clauses with AI..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-80 pl-10 h-10 bg-slate-50/80 border-slate-200 rounded-lg focus:bg-white"
                    data-testid="dashboard-search-input"
                  />
                </div>
              </form>
            </div>

            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" className="text-slate-400 hover:text-slate-600 hover:bg-slate-100">
                <Bell className="w-5 h-5" />
              </Button>
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="flex items-center gap-2.5 px-2 hover:bg-slate-100" data-testid="user-menu-btn">
                    <Avatar className="w-8 h-8">
                      <AvatarImage src={user?.picture} alt={user?.name} />
                      <AvatarFallback className="bg-gradient-to-br from-teal-500 to-emerald-500 text-white text-sm font-medium">
                        {user?.name?.charAt(0) || "U"}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden md:inline text-sm font-medium text-slate-700">
                      {user?.name}
                    </span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56 rounded-xl shadow-lg border border-slate-200/60">
                  <div className="px-3 py-3">
                    <p className="text-sm font-medium text-slate-800">{user?.name}</p>
                    <p className="text-xs text-slate-500">{user?.email}</p>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/settings")} className="cursor-pointer">
                    <Settings className="w-4 h-4 mr-2" />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-red-600 cursor-pointer" data-testid="logout-btn">
                    <LogOut className="w-4 h-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="font-semibold text-2xl text-slate-800 mb-1 tracking-tight">
            Welcome back, {user?.name?.split(" ")[0]}
          </h1>
          <p className="text-slate-500">
            Manage your contracts and stay compliant with federal regulations.
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-4 mb-10">
          {quickActions.map((action, index) => (
            <button
              key={action.label}
              onClick={action.loading ? undefined : action.onClick}
              disabled={action.loading}
              className={`group modern-card p-5 text-left hover:border-teal-200 transition-all duration-200 ${action.loading ? 'opacity-75 cursor-wait' : ''}`}
              data-testid={`quick-action-${index}`}
            >
              <div className={`w-10 h-10 bg-gradient-to-br ${action.color} rounded-xl flex items-center justify-center mb-3 shadow-sm group-hover:scale-105 transition-transform`}>
                {action.loading ? (
                  <Loader2 className="w-5 h-5 text-white animate-spin" />
                ) : (
                  <action.icon className="w-5 h-5 text-white" />
                )}
              </div>
              <span className="font-medium text-slate-800 text-sm block">{action.label}</span>
              <span className="text-xs text-slate-400">{action.loading ? "Syncing..." : action.desc}</span>
            </button>
          ))}
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Contracts Section */}
          <div className="lg:col-span-2">
            <div className="modern-card overflow-hidden">
              <div className="flex items-center justify-between p-5 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-gradient-to-br from-teal-50 to-emerald-50 rounded-lg flex items-center justify-center">
                    <FileText className="w-5 h-5 text-teal-600" />
                  </div>
                  <h2 className="font-semibold text-lg text-slate-800">Recent Contracts</h2>
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => navigate("/upload")}
                  className="rounded-lg border-slate-200 hover:border-teal-300 hover:bg-teal-50/50"
                  data-testid="upload-contract-btn"
                >
                  <Plus className="w-4 h-4 mr-1.5" />
                  Upload
                </Button>
              </div>
              
              <div className="divide-y divide-slate-100">
                {loading ? (
                  <div className="p-8 text-center">
                    <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-slate-500 text-sm">Loading contracts...</p>
                  </div>
                ) : contracts.length === 0 ? (
                  <div className="p-12 text-center">
                    <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                      <FileText className="w-8 h-8 text-slate-300" />
                    </div>
                    <p className="text-slate-600 font-medium mb-1">No contracts yet</p>
                    <p className="text-slate-400 text-sm mb-5">Upload your first contract to get started</p>
                    <Button 
                      onClick={() => navigate("/upload")} 
                      className="bg-teal-600 hover:bg-teal-700"
                      data-testid="upload-first-contract-btn"
                    >
                      <Upload className="w-4 h-4 mr-2" />
                      Upload Contract
                    </Button>
                  </div>
                ) : (
                  contracts.slice(0, 5).map((contract) => (
                    <div
                      key={contract.contract_id}
                      className="p-4 hover:bg-slate-50/50 cursor-pointer transition-colors group"
                      onClick={() => navigate(`/contract/${contract.contract_id}`)}
                      data-testid={`contract-${contract.contract_id}`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                            <FileText className="w-5 h-5 text-slate-500" />
                          </div>
                          <div>
                            <p className="font-medium text-slate-800 text-sm">{contract.name}</p>
                            <p className="text-xs text-slate-400">
                              {contract.clauses_found?.length || 0} clauses found
                            </p>
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-teal-500 transition-colors" />
                      </div>
                    </div>
                  ))
                )}
              </div>
              
              {contracts.length > 5 && (
                <div className="p-4 border-t border-slate-100 text-center">
                  <Button variant="ghost" size="sm" className="text-teal-600 hover:text-teal-700">
                    View all contracts
                    <ArrowRight className="w-4 h-4 ml-1" />
                  </Button>
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Favorites */}
            <div className="modern-card overflow-hidden">
              <div className="flex items-center gap-3 p-5 border-b border-slate-100">
                <div className="w-9 h-9 bg-gradient-to-br from-amber-50 to-orange-50 rounded-lg flex items-center justify-center">
                  <Star className="w-5 h-5 text-amber-500" />
                </div>
                <h2 className="font-semibold text-slate-800">Favorite Clauses</h2>
              </div>
              
              <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
                {favorites.length === 0 ? (
                  <div className="p-6 text-center">
                    <Star className="w-10 h-10 text-slate-200 mx-auto mb-2" />
                    <p className="text-slate-400 text-sm">No favorites yet</p>
                  </div>
                ) : (
                  favorites.slice(0, 5).map((fav) => (
                    <div
                      key={fav.clause_id}
                      className="p-3 hover:bg-slate-50/50 transition-colors group"
                    >
                      <div className="flex items-center justify-between">
                        <div 
                          className="flex-1 cursor-pointer"
                          onClick={() => navigate(`/clause/${fav.clause_id}`)}
                        >
                          <p className="font-mono text-sm text-teal-600 font-medium">
                            {fav.clause?.number}
                          </p>
                          <p className="text-xs text-slate-500 truncate">
                            {fav.clause?.title}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            removeFavorite(fav.clause_id);
                          }}
                          className="p-1.5 hover:bg-red-50 rounded-lg text-slate-300 hover:text-red-500 transition-colors"
                          data-testid={`remove-fav-${fav.clause_id}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Saved Searches */}
            <div className="modern-card overflow-hidden">
              <div className="flex items-center gap-3 p-5 border-b border-slate-100">
                <div className="w-9 h-9 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg flex items-center justify-center">
                  <Clock className="w-5 h-5 text-blue-500" />
                </div>
                <h2 className="font-semibold text-slate-800">Saved Searches</h2>
              </div>
              
              <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
                {savedSearches.length === 0 ? (
                  <div className="p-6 text-center">
                    <Clock className="w-10 h-10 text-slate-200 mx-auto mb-2" />
                    <p className="text-slate-400 text-sm">No saved searches</p>
                  </div>
                ) : (
                  savedSearches.slice(0, 5).map((search) => (
                    <div
                      key={search.search_id}
                      className="p-3 hover:bg-slate-50/50 transition-colors group"
                    >
                      <div className="flex items-center justify-between">
                        <div 
                          className="flex-1 cursor-pointer"
                          onClick={() => navigate(`/search?q=${encodeURIComponent(search.query)}`)}
                        >
                          <p className="text-sm text-slate-700 font-medium">{search.query}</p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteSavedSearch(search.search_id);
                          }}
                          className="p-1.5 hover:bg-red-50 rounded-lg text-slate-300 hover:text-red-500 transition-colors"
                          data-testid={`delete-search-${search.search_id}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
