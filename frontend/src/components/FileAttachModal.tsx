import React, { useState, useRef, useEffect } from 'react';
import { Upload, FileSpreadsheet, X } from 'lucide-react';
import { formatFileSize } from '../utils/formatters';

interface FileAttachModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (file: File) => void;
  currentFile?: File | null;
}

function isValidTabularFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith('.csv') || lower.endsWith('.xlsx') || lower.endsWith('.xls');
}

export const FileAttachModal: React.FC<FileAttachModalProps> = ({
  isOpen,
  onClose,
  onSelectFile,
  currentFile,
}) => {
  if (!isOpen) return null;

  return (
    <FileAttachModalContent
      onClose={onClose}
      onSelectFile={onSelectFile}
      currentFile={currentFile}
    />
  );
};

interface FileAttachModalContentProps {
  onClose: () => void;
  onSelectFile: (file: File) => void;
  currentFile?: File | null;
}

const FileAttachModalContent: React.FC<FileAttachModalContentProps> = ({
  onClose,
  onSelectFile,
  currentFile,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(currentFile || null);
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleFile = (file: File) => {
    if (!isValidTabularFile(file.name)) {
      setErrorMessage('Please select a valid CSV or Excel file (.csv, .xlsx, .xls)');
      return;
    }
    setErrorMessage(null);
    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
    e.target.value = '';
  };

  const handleConfirm = () => {
    if (selectedFile) {
      onSelectFile(selectedFile);
      onClose();
    }
  };

  return (
    <div onClick={onClose} className="modal-backdrop">
      <div onClick={(e) => e.stopPropagation()} className="modal-dialog">
        <div className="modal-header">
          <span className="modal-title">Attach Dataset File</span>
          <button onClick={onClose} className="icon-action-btn" title="Close">
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleInputChange}
            accept=".csv,.xlsx,.xls"
            style={{ display: 'none' }}
          />

          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`dropzone ${isDragging ? 'dragging' : ''}`}
          >
            <div className="dropzone-icon">
              <Upload size={20} />
            </div>
            <div>
              <p style={{ fontSize: '13px', fontWeight: 600, color: '#f8f9fa', marginBottom: '4px' }}>
                Drag and drop your file here, or browse
              </p>
              <p style={{ fontSize: '11.5px', color: '#adb5bd' }}>
                Supports CSV and Excel files (.csv, .xlsx, .xls)
              </p>
            </div>
          </div>

          {errorMessage && <div className="error-banner">{errorMessage}</div>}

          {selectedFile && (
            <div className="file-card">
              <div className="session-item-main">
                <FileSpreadsheet size={18} color="#f8f9fa" style={{ flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <p className="session-title" style={{ color: '#f8f9fa', fontWeight: 600 }} title={selectedFile.name}>
                    {selectedFile.name}
                  </p>
                  <p style={{ fontSize: '11px', color: '#adb5bd' }}>
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedFile(null);
                }}
                className="icon-action-btn"
                title="Remove file"
              >
                <X size={15} />
              </button>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button onClick={handleConfirm} disabled={!selectedFile} className="btn-primary">
            Attach File
          </button>
        </div>
      </div>
    </div>
  );
};
