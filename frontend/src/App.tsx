import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "./api";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Agents from "./pages/Agents";
import Accounts from "./pages/Accounts";
import Grants from "./pages/Grants";

export default function App() {
  const { i18n } = useTranslation();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });

  useEffect(() => {
    if (me.data && me.data.language !== i18n.language) i18n.changeLanguage(me.data.language);
  }, [me.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (me.isLoading) {
    return <div className="h-full flex items-center justify-center"><span className="w-8 h-8 rounded-full border-2 border-line border-t-brand animate-spin" /></div>;
  }
  if (!me.data) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout user={me.data} />}>
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:agentId" element={<Chat />} />
        <Route path="/chat/:agentId/:threadId" element={<Chat />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/agents/:agentId" element={<Agents />} />
        <Route path="/grants" element={<Grants />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  );
}
