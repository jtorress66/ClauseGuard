import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Download, FileText, FileJson, Table,
  CheckCircle, Loader2, Search
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
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

export default function BatchExport({ user }) {
  const navigate = useNavigate();
  const [clauses, setClauses] = useState([]);
  const [selectedClauses, setSelectedClauses] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState("pdf");
  const [includeFullText, setIncludeFullText] = useState(true);
  const [includeFlowdown, setIncludeFlowdown] = useState(true);

  useEffect(() => {
    fetchClauses();
  }, []);

  const fetchClauses = async () => {
    try {
      const response = await fetch(`${API}/clauses/search?query=&limit=100`);
      if (response.ok) {
        const data = await response.json();
        setClauses(data.clauses || []);
      }
    } catch (error) {
      toast.error("Failed to fetch clauses");
    } finally {
      setLoading(false);
    }
  };

  const toggleClause = (clauseNumber) => {
    setSelectedClauses(prev => 
      prev.includes(clauseNumber)
        ? prev.filter(c => c !== clauseNumber)
        : [...prev, clauseNumber]
    );
  };

  const selectAll = () => {
    if (selectedClauses.length === filteredClauses.length) {
      setSelectedClauses([]);
    } else {
      setSelectedClauses(filteredClauses.map(c => c.number));
    }
  };

  const handleExport = async () => {
    if (selectedClauses.length === 0) {
      toast.error("Please select at least one clause to export");
      return;
    }

    setExporting(true);

    try {
      const response = await fetch(`${API}/export/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          clause_numbers: selectedClauses,
          clause_ids: [],
          include_full_text: includeFullText,
          include_flowdown_info: includeFlowdown,
          format: exportFormat
        })
      });

      if (response.ok) {
        if (exportFormat === "json") {
          const data = await response.json();
          // Download as JSON file
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `clauses_export_${Date.now()}.json`;
          a.click();
        } else {
          // PDF or CSV - download as blob
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `clauses_export_${Date.now()}.${exportFormat}`;
          a.click();
        }
        toast.success(`Exported ${selectedClauses.length} clauses as ${exportFormat.toUpperCase()}`);
      } else {
        toast.error("Export failed");
      }
    } catch (error) {
      toast.error("Export failed");
    } finally {
      setExporting(false);
    }
  };

  const filteredClauses = clauses.filter(clause => 
    searchQuery === "" ||
    clause.number.toLowerCase().includes(searchQuery.toLowerCase()) ||
    clause.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    clause.type.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
            Batch Export
          </h1>
          <p className="text-slate-600">
            Select multiple clauses to export as PDF, JSON, or CSV
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Export Options */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl border border-slate-200 p-6 sticky top-24">
              <h2 className="font-heading font-bold text-lg text-navy-900 mb-4">
                Export Options
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-navy-700 mb-2">
                    Format
                  </label>
                  <Select value={exportFormat} onValueChange={setExportFormat}>
                    <SelectTrigger data-testid="format-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pdf">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4" />
                          PDF Document
                        </div>
                      </SelectItem>
                      <SelectItem value="json">
                        <div className="flex items-center gap-2">
                          <FileJson className="w-4 h-4" />
                          JSON Data
                        </div>
                      </SelectItem>
                      <SelectItem value="csv">
                        <div className="flex items-center gap-2">
                          <Table className="w-4 h-4" />
                          CSV Spreadsheet
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={includeFullText}
                      onCheckedChange={setIncludeFullText}
                      data-testid="include-text-checkbox"
                    />
                    <span className="text-sm text-navy-700">Include full text</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={includeFlowdown}
                      onCheckedChange={setIncludeFlowdown}
                      data-testid="include-flowdown-checkbox"
                    />
                    <span className="text-sm text-navy-700">Include flowdown info</span>
                  </label>
                </div>

                <div className="pt-4 border-t border-slate-200">
                  <p className="text-sm text-slate-500 mb-3">
                    Selected: <span className="font-bold text-navy-900">{selectedClauses.length}</span> clauses
                  </p>
                  
                  <Button
                    onClick={handleExport}
                    disabled={exporting || selectedClauses.length === 0}
                    className="w-full bg-teal-600 hover:bg-teal-700"
                    data-testid="export-btn"
                  >
                    {exporting ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Exporting...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4 mr-2" />
                        Export {exportFormat.toUpperCase()}
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Clause Selection */}
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl border border-slate-200">
              {/* Search & Select All */}
              <div className="p-4 border-b border-slate-200">
                <div className="flex flex-col sm:flex-row gap-4">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      placeholder="Search clauses..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                      data-testid="search-input"
                    />
                  </div>
                  <Button variant="outline" onClick={selectAll} data-testid="select-all-btn">
                    {selectedClauses.length === filteredClauses.length ? "Deselect All" : "Select All"}
                  </Button>
                </div>
              </div>

              {/* Clause List */}
              <div className="max-h-[600px] overflow-y-auto">
                {loading ? (
                  <div className="p-8 text-center">
                    <Loader2 className="w-8 h-8 animate-spin text-teal-600 mx-auto" />
                  </div>
                ) : filteredClauses.length === 0 ? (
                  <div className="p-8 text-center text-slate-500">
                    No clauses found
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {filteredClauses.map(clause => (
                      <label
                        key={clause.clause_id}
                        className={`flex items-start gap-4 p-4 cursor-pointer hover:bg-slate-50 transition-colors ${
                          selectedClauses.includes(clause.number) ? "bg-teal-50" : ""
                        }`}
                      >
                        <Checkbox
                          checked={selectedClauses.includes(clause.number)}
                          onCheckedChange={() => toggleClause(clause.number)}
                          className="mt-1"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono font-semibold text-teal-700">
                              {clause.number}
                            </span>
                            <Badge 
                              variant="secondary"
                              className={clause.type === "FAR" ? "bg-teal-100 text-teal-700" : "bg-navy-100 text-navy-700"}
                            >
                              {clause.type}
                            </Badge>
                            {clause.flowdown_required && (
                              <Badge variant="outline" className="border-amber-300 text-amber-700">
                                Flowdown
                              </Badge>
                            )}
                          </div>
                          <p className="text-navy-900 text-sm line-clamp-1">
                            {clause.title}
                          </p>
                        </div>
                        {selectedClauses.includes(clause.number) && (
                          <CheckCircle className="w-5 h-5 text-teal-600 flex-shrink-0" />
                        )}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
