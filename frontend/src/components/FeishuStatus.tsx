import { useState, useEffect } from "react";

interface FeishuStatusProps {
  agentId: number;
}

export function FeishuStatus({ agentId }: FeishuStatusProps) {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/feishu/status/${agentId}`);
      if (!res.ok) return;
      const data = await res.json();
      setConnected(data.connected);
    } catch {
      setConnected(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // 每10s轮询
    return () => clearInterval(interval);
  }, [agentId]);

  const handleConnect = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/feishu/connect/${agentId}`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setConnected(true);
      } else {
        setError("连接失败，请检查 App ID 和 Secret 是否正确");
      }
    } catch {
      setError("网络错误");
    }
    setLoading(false);
  };

  const handleDisconnect = async () => {
    setLoading(true);
    try {
      await fetch(`/api/feishu/disconnect/${agentId}`, { method: "POST" });
      setConnected(false);
    } catch {
      setError("断开失败");
    }
    setLoading(false);
  };

  return (
    <div className="flex items-center gap-3 text-sm mt-4 pt-3 border-t border-gray-200">
      <span className="font-medium text-gray-600">飞书连接状态：</span>
      <span className={`flex items-center gap-1.5 ${connected ? "text-green-600" : "text-gray-400"}`}>
        <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-gray-300"}`} />
        {connected ? "已连接" : "未连接"}
      </span>
      {connected ? (
        <button
          onClick={handleDisconnect}
          disabled={loading}
          className="ml-auto px-3 py-1 text-xs border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-50"
        >
          {loading ? "断开中..." : "断开连接"}
        </button>
      ) : (
        <button
          onClick={handleConnect}
          disabled={loading}
          className="ml-auto px-3 py-1 text-xs border border-blue-300 text-blue-600 rounded hover:bg-blue-50 disabled:opacity-50"
        >
          {loading ? "连接中..." : "手动连接"}
        </button>
      )}
      {error && <span className="text-xs text-red-500 ml-2">{error}</span>}
    </div>
  );
}
