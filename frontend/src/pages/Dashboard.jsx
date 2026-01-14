import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  Search, FileText, Download, LogOut, Star, 
  Clock, Upload, ChevronRight, BarChart3, BookOpen, 
  Bell, Settings, Plus, Trash2
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

  const quickActions = [
    { icon: Search, label: "AI Clause Search", onClick: () => navigate("/search?ai=true"), color: "bg-teal-600" },
    { icon: Upload, label: "Upload Contract", onClick: () => navigate("/upload"), color: "bg-navy-700" },
    { icon: Download, label: "Flowdown Analysis", onClick: () => navigate("/flowdown"), color: "bg-amber-600" },
    { icon: FileText, label: "Compare Contracts", onClick: () => navigate("/compare"), color: "bg-purple-600" }
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 md:px-12">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate("/")}>
                <ClauseGuardLogo className="w-8 h-8" variant="light" />
                <span className="font-heading font-bold text-xl text-navy-900">ClauseGuard</span>
              </div>
              
              <form onSubmit={handleSearch} className="hidden md:flex">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    type="text"
                    placeholder="Search clauses with AI..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-80 pl-10 h-10 bg-slate-50 border-slate-200"
                    data-testid="dashboard-search-input"
                  />
                </div>
              </form>
            </div>

            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon" className="text-slate-500">
                <Bell className="w-5 h-5" />
              </Button>
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="flex items-center gap-2 px-2" data-testid="user-menu-btn">
                    <Avatar className="w-8 h-8">
                      <AvatarImage src={user?.picture} alt={user?.name} />
                      <AvatarFallback className="bg-teal-100 text-teal-700">
                        {user?.name?.charAt(0) || "U"}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden md:inline text-sm font-medium text-navy-900">
                      {user?.name}
                    </span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <div className="px-3 py-2">
                    <p className="text-sm font-medium">{user?.name}</p>
                    <p className="text-xs text-slate-500">{user?.email}</p>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/settings")}>
                    <Settings className="w-4 h-4 mr-2" />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-red-600" data-testid="logout-btn">
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
          <h1 className="font-heading font-bold text-2xl text-navy-900 mb-2">
            Welcome back, {user?.name?.split(" ")[0]}
          </h1>
          <p className="text-slate-600">
            Manage your contracts and stay compliant with federal regulations.
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {quickActions.map((action, index) => (
            <button
              key={action.label}
              onClick={action.onClick}
              className="dashboard-card bg-white rounded-xl p-6 border border-slate-200 text-left hover:border-teal-200 transition-all"
              data-testid={`quick-action-${index}`}
            >
              <div className={`w-12 h-12 ${action.color} rounded-lg flex items-center justify-center mb-4`}>
                <action.icon className="w-6 h-6 text-white" />
              </div>
              <span className="font-medium text-navy-900">{action.label}</span>
            </button>
          ))}
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Contracts Section */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="flex items-center justify-between p-6 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <FileText className="w-5 h-5 text-teal-600" />
                  <h2 className="font-heading font-bold text-lg text-navy-900">Recent Contracts</h2>
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => navigate("/upload")}
                  data-testid="upload-contract-btn"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Upload
                </Button>
              </div>
              
              <div className="divide-y divide-slate-100">
                {loading ? (
                  <div className="p-6 text-center text-slate-500">Loading...</div>
                ) : contracts.length === 0 ? (
                  <div className="p-12 text-center">
                    <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 mb-4">No contracts uploaded yet</p>
                    <Button onClick={() => navigate("/upload")} data-testid="upload-first-contract-btn">
                      Upload Your First Contract
                    </Button>
                  </div>
                ) : (
                  contracts.slice(0, 5).map((contract) => (
                    <div 
                      key={contract.contract_id}
                      className="p-4 hover:bg-slate-50 cursor-pointer flex items-center justify-between"
                      onClick={() => navigate(`/contract/${contract.contract_id}`)}
                      data-testid={`contract-${contract.contract_id}`}
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                          <FileText className="w-5 h-5 text-slate-500" />
                        </div>
                        <div>
                          <p className="font-medium text-navy-900">{contract.name}</p>
                          <p className="text-sm text-slate-500">
                            {contract.clauses_found?.length || 0} clauses found
                          </p>
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-slate-400" />
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Favorites */}
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="flex items-center gap-3 p-6 border-b border-slate-100">
                <Star className="w-5 h-5 text-amber-500" />
                <h2 className="font-heading font-bold text-lg text-navy-900">Favorite Clauses</h2>
              </div>
              
              <div className="p-4">
                {favorites.length === 0 ? (
                  <p className="text-slate-500 text-sm text-center py-4">
                    No favorites yet. Star clauses to save them here.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {favorites.slice(0, 5).map((fav) => (
                      <div 
                        key={fav.favorite_id}
                        className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50"
                      >
                        <button
                          onClick={() => navigate(`/clause/${fav.clause?.clause_id}`)}
                          className="text-left"
                        >
                          <span className="font-mono text-sm text-teal-700">{fav.clause?.number}</span>
                          <p className="text-xs text-slate-500 truncate max-w-[180px]">
                            {fav.clause?.title}
                          </p>
                        </button>
                        <button
                          onClick={() => removeFavorite(fav.clause_id)}
                          className="p-1 text-slate-400 hover:text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Saved Searches */}
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="flex items-center gap-3 p-6 border-b border-slate-100">
                <Clock className="w-5 h-5 text-slate-500" />
                <h2 className="font-heading font-bold text-lg text-navy-900">Saved Searches</h2>
              </div>
              
              <div className="p-4">
                {savedSearches.length === 0 ? (
                  <p className="text-slate-500 text-sm text-center py-4">
                    Save your searches for quick access.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {savedSearches.slice(0, 5).map((search) => (
                      <div 
                        key={search.search_id}
                        className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50"
                      >
                        <button
                          onClick={() => navigate(`/search?q=${encodeURIComponent(search.query)}`)}
                          className="text-sm text-navy-700 hover:text-teal-600"
                        >
                          {search.query}
                        </button>
                        <button
                          onClick={() => deleteSavedSearch(search.search_id)}
                          className="p-1 text-slate-400 hover:text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Stats Card */}
            <div className="bg-gradient-to-br from-teal-600 to-teal-700 rounded-xl p-6 text-white">
              <div className="flex items-center gap-3 mb-4">
                <BarChart3 className="w-5 h-5" />
                <h3 className="font-heading font-bold">Quick Stats</h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-teal-100">Contracts</span>
                  <span className="font-bold">{contracts.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-teal-100">Favorites</span>
                  <span className="font-bold">{favorites.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-teal-100">Saved Searches</span>
                  <span className="font-bold">{savedSearches.length}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
