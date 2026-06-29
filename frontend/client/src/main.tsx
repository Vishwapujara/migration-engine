import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { LandingPage } from "@/pages/LandingPage";
import { JobsPage } from "@/pages/JobsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { PlanPage } from "@/pages/PlanPage";
import { FileDetailPage } from "@/pages/FileDetailPage";
import { ReportPage } from "@/pages/ReportPage";
import { ReviewPage } from "@/pages/ReviewPage";
import "@/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId/review" element={<ReviewPage />} />
          <Route path="/jobs/:jobId" element={<DashboardPage />} />
          <Route path="/jobs/:jobId/plan" element={<PlanPage />} />
          <Route path="/jobs/:jobId/files/*" element={<FileDetailPage />} />
          <Route path="/jobs/:jobId/report" element={<ReportPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </React.StrictMode>
);
