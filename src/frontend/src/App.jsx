import { Routes, Route, NavLink } from "react-router-dom";
import Jobs from "./pages/Jobs.jsx";
import Resumes from "./pages/Resumes.jsx";
import ResumeEdit from "./pages/ResumeEdit.jsx";
import Journal from "./pages/Journal.jsx";
import Config from "./pages/Config.jsx";
import Funded from "./pages/Funded.jsx";
import InterviewPrep from "./pages/InterviewPrep.jsx";
import Outreach from "./pages/Outreach.jsx";
import Campaigns from "./pages/Campaigns.jsx";

function Layout({ children }) {
  const linkClass = ({ isActive }) =>
    `px-3 py-2 rounded text-sm font-medium transition-colors ${
      isActive
        ? "bg-emerald-600 text-white"
        : "text-slate-300 hover:text-white hover:bg-slate-700"
    }`;

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <nav className="bg-slate-800 border-b border-slate-700 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <span className="text-emerald-400 font-bold text-lg tracking-tight">
            🦞 OpenClaw
          </span>
          <div className="flex gap-1">
            <NavLink to="/" className={linkClass} end>
              Jobs
            </NavLink>
            <NavLink to="/funded" className={linkClass}>
              Funded
            </NavLink>
            <NavLink to="/campaigns" className={linkClass}>
              Campaigns
            </NavLink>
            <NavLink to="/resumes" className={linkClass}>
              Resumes
            </NavLink>
            <NavLink to="/resume-edit" className={linkClass}>
              Edit Resume
            </NavLink>
            <NavLink to="/journal" className={linkClass}>
              Journal
            </NavLink>
            <NavLink to="/interview" className={linkClass}>
              Interview
            </NavLink>
            <NavLink to="/outreach" className={linkClass}>
              Outreach
            </NavLink>
            <NavLink to="/config" className={linkClass}>
              Config
            </NavLink>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Layout>
            <Jobs />
          </Layout>
        }
      />
      <Route
        path="/funded"
        element={
          <Layout>
            <Funded />
          </Layout>
        }
      />
      <Route
        path="/campaigns"
        element={
          <Layout>
            <Campaigns />
          </Layout>
        }
      />
      <Route
        path="/resumes"
        element={
          <Layout>
            <Resumes />
          </Layout>
        }
      />
      <Route
        path="/resume-edit"
        element={
          <Layout>
            <ResumeEdit />
          </Layout>
        }
      />
      <Route
        path="/journal"
        element={
          <Layout>
            <Journal />
          </Layout>
        }
      />
      <Route
        path="/interview"
        element={
          <Layout>
            <InterviewPrep />
          </Layout>
        }
      />
      <Route
        path="/outreach"
        element={
          <Layout>
            <Outreach />
          </Layout>
        }
      />
      <Route
        path="/config"
        element={
          <Layout>
            <Config />
          </Layout>
        }
      />
    </Routes>
  );
}
