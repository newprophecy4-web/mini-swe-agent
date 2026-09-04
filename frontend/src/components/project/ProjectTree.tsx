import React, { useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Folder,
  FolderOpen,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { TreeItem } from '../../types/agent';
import { safeFileName } from '../../utils/security';

interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children: Record<string, TreeNode>;
}

export const ProjectTree: React.FC = () => {
  const [state, setState] = useSessionStore();
  const [filterText, setFilterText] = useState('');
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({ '': true });
  const [isSearchingText, setIsSearchingText] = useState(false);
  const [contentSearchQuery, setContentSearchQuery] = useState('');
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Build tree hierarchy from flat path list
  const rootNode = useMemo(() => {
    const root: TreeNode = { name: '', path: '', type: 'directory', children: {} };

    state.projectTree.forEach((item) => {
      const parts = item.path.split('/');
      let current = root;

      parts.forEach((part, index) => {
        const currentPath = parts.slice(0, index + 1).join('/');
        const isLeaf = index === parts.length - 1;

        if (!current.children[part]) {
          current.children[part] = {
            name: part,
            path: currentPath,
            type: isLeaf ? item.type : 'directory',
            children: {},
          };
        }
        current = current.children[part];
      });
    });

    return root;
  }, [state.projectTree]);

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  const handleSelectFile = async (path: string) => {
    const sessionId = state.activeSessionId || state.projectSessionId || state.workSessionId;
    if (!sessionId) return;

    setState({ selectedFile: path, isFileLoading: true, selectedFileContent: null });

    try {
      const res = await agentApi.readFile({
        session_id: sessionId,
        path,
      });

      if (res.ok) {
        setState({
          selectedFile: res.path,
          selectedFileContent: res.content,
          isFileLoading: false,
        });
      }
    } catch (err: any) {
      setState({
        selectedFileContent: `// Failed to load ${path}: ${err?.message || 'Unknown error'}`,
        isFileLoading: false,
      });
    }
  };

  const handleSearchWorkspaceContent = async (e: React.FormEvent) => {
    e.preventDefault();
    const sessionId = state.activeSessionId || state.projectSessionId || state.workSessionId;
    if (!sessionId || !contentSearchQuery.trim()) return;

    setIsSearchingText(true);
    setSearchError(null);

    try {
      const res = await agentApi.searchFiles({
        session_id: sessionId,
        query: contentSearchQuery.trim(),
      });

      if (res.ok) {
        setState({ searchResults: res.results || [] });
      }
    } catch (err: any) {
      setSearchError(err?.message || 'Search failed');
    } finally {
      setIsSearchingText(false);
    }
  };

  const renderTree = (node: TreeNode, depth = 0) => {
    const entries = Object.values(node.children);

    return (
      <div className="space-y-0.5">
        {entries.map((child) => {
          const isDir = child.type === 'directory';
          const isExpanded = Boolean(expandedFolders[child.path]);
          const isSelected = state.selectedFile === child.path;

          // Filter by name
          if (filterText && !child.path.toLowerCase().includes(filterText.toLowerCase())) {
            return null;
          }

          return (
            <div key={child.path}>
              <div
                id={`tree-item-${child.path.replace(/[/.]/g, '-')}`}
                onClick={() => {
                  if (isDir) {
                    toggleFolder(child.path);
                  } else {
                    handleSelectFile(child.path);
                  }
                }}
                style={{ paddingLeft: `${depth * 14 + 10}px` }}
                className={`flex items-center gap-1.5 py-1 pr-2 rounded text-xs cursor-pointer select-none transition-colors group ${
                  isSelected
                    ? 'bg-zinc-800/80 text-zinc-100 font-medium border-l-2 border-indigo-500'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
                }`}
              >
                {isDir ? (
                  <>
                    <span className="w-3.5 h-3.5 flex items-center justify-center text-zinc-500 group-hover:text-zinc-300">
                      {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    </span>
                    {isExpanded ? (
                      <FolderOpen className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                    ) : (
                      <Folder className="w-3.5 h-3.5 text-indigo-400/80 shrink-0" />
                    )}
                  </>
                ) : (
                  <>
                    <span className="w-3.5 h-3.5" />
                    <FileCode2 className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-indigo-400' : 'text-zinc-500 group-hover:text-zinc-400'}`} />
                  </>
                )}
                <span className="truncate text-[11px] font-mono">{child.name}</span>
              </div>

              {isDir && isExpanded && renderTree(child, depth + 1)}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div id="project-tree-container" className="flex flex-col h-full bg-[#09090b] border-r border-zinc-800">
      {/* Header with Search & Controls */}
      <div className="p-2.5 border-b border-zinc-800 space-y-2 bg-[#09090b]">
        <div className="flex items-center justify-between text-xs text-zinc-300">
          <span className="font-bold uppercase tracking-widest text-[10px] text-zinc-500">
            Explorer
          </span>
          <div className="flex items-center gap-1">
            <button
              id="tree-search-modal-btn"
              onClick={() => setSearchModalOpen(true)}
              className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 rounded transition-colors cursor-pointer"
              title="Search code within workspace"
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Filter input */}
        <div className="relative">
          <input
            id="tree-filter-input"
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter files..."
            className="w-full px-2 py-1 text-xs bg-zinc-900 border border-zinc-800 rounded text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 font-mono"
          />
          {filterText && (
            <button
              onClick={() => setFilterText('')}
              className="absolute right-1.5 top-1.5 text-zinc-500 hover:text-zinc-300 cursor-pointer"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-y-auto p-2">
        {state.projectTree.length === 0 ? (
          <div className="py-10 px-3 text-center text-zinc-500 text-xs select-none">
            <p className="font-medium text-zinc-400 mb-1">No Workspace Loaded</p>
            <p className="text-[11px]">
              Inspect a GitHub repository or upload a ZIP file from the sidebar to browse files.
            </p>
          </div>
        ) : (
          renderTree(rootNode)
        )}
      </div>

      {/* Code Search Modal */}
      {searchModalOpen && (
        <div
          id="code-search-modal"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
        >
          <div className="w-full max-w-lg bg-[#09090b] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
            <div className="p-3 border-b border-zinc-800 flex items-center justify-between bg-[#09090b]">
              <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
                <Search className="w-4 h-4 text-indigo-400" />
                Search in Workspace Files
              </div>
              <button
                onClick={() => setSearchModalOpen(false)}
                className="p-1 text-zinc-400 hover:text-zinc-100 rounded cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSearchWorkspaceContent} className="p-3 border-b border-zinc-800 flex gap-2 bg-zinc-950/40">
              <input
                id="code-search-input"
                type="text"
                value={contentSearchQuery}
                onChange={(e) => setContentSearchQuery(e.target.value)}
                placeholder="Search function, symbol, or keyword..."
                className="flex-1 px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <button
                id="code-search-submit-btn"
                type="submit"
                disabled={isSearchingText || !contentSearchQuery.trim()}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg transition-colors cursor-pointer shadow-md shadow-indigo-500/20"
              >
                {isSearchingText ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Search'}
              </button>
            </form>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-zinc-950/30">
              {searchError && (
                <div className="p-2 text-xs text-rose-400 bg-rose-950/40 rounded-lg border border-rose-800">
                  {searchError}
                </div>
              )}

              {state.searchResults.length === 0 ? (
                <div className="py-8 text-center text-xs text-zinc-500">
                  {isSearchingText ? 'Searching code...' : 'Enter a query to search workspace files'}
                </div>
              ) : (
                <div className="space-y-1.5">
                  <div className="text-[11px] text-zinc-400 font-mono mb-2">
                    Found {state.searchResults.length} matches:
                  </div>
                  {state.searchResults.map((item, index) => (
                    <div
                      key={index}
                      onClick={() => {
                        handleSelectFile(item.path);
                        setSearchModalOpen(false);
                      }}
                      className="p-2 rounded-lg bg-zinc-900/60 border border-zinc-800 hover:border-indigo-500/50 cursor-pointer text-xs group transition-colors"
                    >
                      <div className="flex items-center justify-between text-zinc-400 font-mono text-[11px]">
                        <span className="text-indigo-400 group-hover:underline">{item.path}</span>
                        <span>Line {item.line}</span>
                      </div>
                      <pre className="mt-1 font-mono text-[11px] text-zinc-300 bg-zinc-950 p-1.5 rounded-md overflow-x-auto border border-zinc-850">
                        {item.text}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
