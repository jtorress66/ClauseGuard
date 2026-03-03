import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { 
  ArrowLeft, Upload, FileText, CheckCircle, 
  AlertCircle, Loader2, X 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { API } from "@/App";
import { ClauseGuardLogo } from "@/components/ClauseGuardLogo";

export default function ContractUpload({ user }) {
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState([]);

  const onDrop = useCallback((acceptedFiles) => {
    setFiles(prev => [...prev, ...acceptedFiles.map(file => ({
      file,
      status: "pending",
      result: null
    }))]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/plain": [".txt"],
      "application/msword": [".doc"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"]
    },
    maxSize: 10 * 1024 * 1024 // 10MB
  });

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  const uploadFiles = async () => {
    if (files.length === 0) {
      toast.error("Please select files to upload");
      return;
    }

    setUploading(true);
    const results = [];

    for (let i = 0; i < files.length; i++) {
      const fileItem = files[i];
      if (fileItem.status === "success") continue;

      setFiles(prev => prev.map((f, idx) => 
        idx === i ? { ...f, status: "uploading" } : f
      ));

      try {
        const formData = new FormData();
        formData.append("file", fileItem.file);

        const response = await fetch(`${API}/contracts/upload`, {
          method: "POST",
          credentials: "include",
          body: formData
        });

        if (response.ok) {
          const data = await response.json();
          setFiles(prev => prev.map((f, idx) => 
            idx === i ? { ...f, status: "success", result: data } : f
          ));
          results.push({ success: true, data });
        } else {
          const error = await response.text();
          setFiles(prev => prev.map((f, idx) => 
            idx === i ? { ...f, status: "error", error } : f
          ));
          results.push({ success: false, error });
        }
      } catch (error) {
        setFiles(prev => prev.map((f, idx) => 
          idx === i ? { ...f, status: "error", error: error.message } : f
        ));
        results.push({ success: false, error: error.message });
      }
    }

    setUploadResults(results);
    setUploading(false);

    const successCount = results.filter(r => r.success).length;
    if (successCount > 0) {
      toast.success(`${successCount} contract(s) uploaded successfully`);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "uploading":
        return <Loader2 className="w-5 h-5 text-teal-600 animate-spin" />;
      case "success":
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case "error":
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <FileText className="w-5 h-5 text-slate-400" />;
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
      <main className="max-w-4xl mx-auto px-6 md:px-12 py-12">
        <div className="text-center mb-8">
          <h1 className="font-heading font-bold text-3xl text-navy-900 mb-2">
            Upload Contract
          </h1>
          <p className="text-slate-600">
            Upload your contracts to analyze clauses and check compliance
          </p>
        </div>

        {/* Upload Zone */}
        <div
          {...getRootProps()}
          className={`upload-zone rounded-xl p-12 text-center cursor-pointer transition-all ${
            isDragActive ? "active border-teal-500 bg-teal-50" : "bg-white"
          }`}
          data-testid="upload-dropzone"
        >
          <input {...getInputProps()} data-testid="file-input" />
          <Upload className={`w-16 h-16 mx-auto mb-4 ${isDragActive ? "text-teal-600" : "text-slate-300"}`} />
          <p className="text-lg font-medium text-navy-900 mb-2">
            {isDragActive ? "Drop files here" : "Drag & drop contracts here"}
          </p>
          <p className="text-slate-500 mb-4">or click to browse</p>
          <p className="text-sm text-slate-400">
            Supports PDF, DOC, DOCX, TXT (max 10MB)
          </p>
        </div>

        {/* File List */}
        {files.length > 0 && (
          <div className="mt-8 bg-white rounded-xl border border-slate-200">
            <div className="p-6 border-b border-slate-100">
              <h2 className="font-heading font-bold text-lg text-navy-900">
                Selected Files ({files.length})
              </h2>
            </div>
            
            <div className="divide-y divide-slate-100">
              {files.map((fileItem, index) => (
                <div key={index} className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {getStatusIcon(fileItem.status)}
                    <div>
                      <p className="font-medium text-navy-900">{fileItem.file.name}</p>
                      <p className="text-sm text-slate-500">
                        {(fileItem.file.size / 1024).toFixed(1)} KB
                      </p>
                      {fileItem.status === "success" && fileItem.result && (
                        <p className="text-sm text-green-600">
                          Found {fileItem.result.clauses_found?.length || 0} clauses
                        </p>
                      )}
                      {fileItem.status === "error" && (
                        <p className="text-sm text-red-500">{fileItem.error}</p>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    {fileItem.status === "success" && fileItem.result && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/contract/${fileItem.result.contract_id}`)}
                        data-testid={`view-contract-${index}`}
                      >
                        View Details
                      </Button>
                    )}
                    {fileItem.status !== "uploading" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeFile(index)}
                        className="text-slate-400 hover:text-red-500"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="p-6 border-t border-slate-100 flex justify-end gap-4">
              <Button
                variant="outline"
                onClick={() => setFiles([])}
                disabled={uploading}
              >
                Clear All
              </Button>
              <Button
                onClick={uploadFiles}
                disabled={uploading || files.every(f => f.status === "success")}
                className="bg-teal-600 hover:bg-teal-700"
                data-testid="upload-btn"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    Upload & Analyze
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Instructions */}
        <div className="mt-8 bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="font-heading font-bold text-navy-900 mb-4">How It Works</h3>
          <ol className="space-y-3 text-slate-600">
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-teal-100 text-teal-700 rounded-full flex items-center justify-center text-sm font-bold">1</span>
              <span>Upload your contract document (PDF, DOC, DOCX, or TXT)</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-teal-100 text-teal-700 rounded-full flex items-center justify-center text-sm font-bold">2</span>
              <span>Our system extracts and identifies all FAR/DFARS clauses</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-teal-100 text-teal-700 rounded-full flex items-center justify-center text-sm font-bold">3</span>
              <span>Get AI-powered compliance analysis and recommendations</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-teal-100 text-teal-700 rounded-full flex items-center justify-center text-sm font-bold">4</span>
              <span>Compare against official requirements and generate reports</span>
            </li>
          </ol>
        </div>
      </main>
    </div>
  );
}
