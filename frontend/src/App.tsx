import { ReviewPage } from "./pages/tree/ReviewPage";
import { Suspense, lazy, useEffect, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { setUnauthenticatedHandler } from "./api/client";
import { authKeys, useMe } from "./api/hooks/auth";
import { normalizeLanguage, storedLanguage } from "./i18n";
import { AppShell } from "./components/layout/AppShell";
import { TreeLayout } from "./components/layout/TreeLayout";
import { Spinner } from "./components/ui/feedback";
import { ChangePasswordRequiredPage, LoginPage, RegisterPage } from "./pages/auth/AuthPages";
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "./pages/auth/EmailPages";
import { AcceptInvitePage, CreateTreePage, TreesListPage } from "./pages/trees/TreesPages";
import { AccountPage } from "./pages/AccountPage";
import { WelcomePage } from "./pages/onboarding/WelcomePage";
import { ClaimInvitePage } from "./pages/onboarding/ClaimInvitePage";
import { DashboardPage } from "./pages/tree/DashboardPage";
import { PeoplePage } from "./pages/tree/PeoplePage";
import { AddPersonPage } from "./pages/tree/AddPersonPage";
import { PersonProfilePage } from "./pages/tree/person/PersonProfilePage";
import { TreeViewerPage } from "./pages/tree/TreeViewerPage";
import { TraditionDetailPage, TraditionsPage } from "./pages/tree/TraditionsPage";
import { RelationshipPage } from "./pages/tree/RelationshipPage";
import { BranchDetailPage, BranchesPage } from "./pages/tree/BranchesPages";
import { HouseholdsPage, JointFamilyPage } from "./pages/tree/HouseholdsPages";
import { PlacesPage } from "./pages/tree/PlacesPage";
import { SourcesPage } from "./pages/tree/SourcesPage";
import { DuplicatesPage, SearchPage } from "./pages/tree/SearchPages";
import { AuditPage, ClaimsPage, InvitationsPage, MembersPage, RestorePeoplePage, SettingsPage } from "./pages/tree/AdminPages";
import { PublicPersonPage, PublicTreePage } from "./pages/public/PublicPages";
import { LandingPage } from "./pages/landing/LandingPage";

// Records modules (documents, property, GEDCOM) are loaded on demand to keep the first load small.
const DocumentsPage = lazy(() => import("./pages/tree/documents/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const DocumentDetailPage = lazy(() => import("./pages/tree/documents/DocumentDetailPage").then((m) => ({ default: m.DocumentDetailPage })));
const PropertyListPage = lazy(() => import("./pages/tree/property/PropertyListPage").then((m) => ({ default: m.PropertyListPage })));
const PropertyDetailPage = lazy(() => import("./pages/tree/property/PropertyDetailPage").then((m) => ({ default: m.PropertyDetailPage })));
// Visualizations, events, reminders and timeline (heritage visualization milestone) load on demand too.
const VisualizationsPage = lazy(() => import("./pages/tree/VisualizationsPage").then((m) => ({ default: m.VisualizationsPage })));
const EventsPage = lazy(() => import("./pages/tree/EventsPage").then((m) => ({ default: m.EventsPage })));
const RemindersPage = lazy(() => import("./pages/tree/RemindersPage").then((m) => ({ default: m.RemindersPage })));
const TimelinePage = lazy(() => import("./pages/tree/TimelinePage").then((m) => ({ default: m.TimelinePage })));
const ImportExportPage = lazy(() => import("./pages/tree/ImportExportPage").then((m) => ({ default: m.ImportExportPage })));

function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Spinner />}>{children}</Suspense>;
}

/** Sends any 401 from the API to the login page (keeping where the user was). */
function AuthRedirector() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  useEffect(() => {
    setUnauthenticatedHandler(() => {
      qc.setQueryData(authKeys.me, null);
      if (!location.pathname.startsWith("/login") && !location.pathname.startsWith("/p/")) {
        navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
      }
    });
    return () => setUnauthenticatedHandler(null);
  }, [navigate, location, qc]);
  return null;
}

/** Applies the signed-in user's saved language unless this browser explicitly chose one. */
function LanguageSync() {
  const me = useMe();
  const { i18n } = useTranslation();
  useEffect(() => {
    if (me.data && !storedLanguage()) {
      const lang = normalizeLanguage(me.data.preferred_language);
      if (!i18n.language.startsWith(lang)) void i18n.changeLanguage(lang);
    }
  }, [me.data, i18n]);
  return null;
}

function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isLoading) return <Spinner />;
  // Signed-out visitors to the home page see the public landing page rather than a sign-in form.
  if (!me.data && location.pathname === "/") return <LandingPage />;
  if (!me.data) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  // A temporary password must be replaced first (the server refuses everything else anyway).
  if (me.data.must_change_password) return <Navigate to="/change-password" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <>
      <AuthRedirector />
      <LanguageSync />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/change-password" element={<ChangePasswordRequiredPage />} />
        <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
        <Route path="/about" element={<LandingPage />} />
        <Route path="/invite/:token" element={<AcceptInvitePage />} />
        <Route path="/claim" element={<ClaimInvitePage />} />
        <Route path="/p/:slug" element={<PublicTreePage />} />
        <Route path="/p/:slug/people/:personId" element={<PublicPersonPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<TreesListPage />} />
            <Route path="/trees/new" element={<CreateTreePage />} />
            <Route path="/welcome" element={<WelcomePage />} />
            <Route path="/account" element={<AccountPage />} />
          </Route>
          <Route path="/t/:treeId" element={<TreeLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="people" element={<PeoplePage />} />
            <Route path="people/new" element={<AddPersonPage />} />
            <Route path="people/:personId" element={<PersonProfilePage />} />
            <Route path="tree" element={<TreeViewerPage />} />
            <Route path="tree/:personId" element={<TreeViewerPage />} />
            <Route path="relationship" element={<RelationshipPage />} />
            <Route path="visualizations" element={<Lazy><VisualizationsPage /></Lazy>} />
            <Route path="events" element={<Lazy><EventsPage /></Lazy>} />
            <Route path="reminders" element={<Lazy><RemindersPage /></Lazy>} />
            <Route path="timeline" element={<Lazy><TimelinePage /></Lazy>} />
            <Route path="joint-family" element={<JointFamilyPage />} />
            <Route path="branches" element={<BranchesPage />} />
            <Route path="branches/:branchId" element={<BranchDetailPage />} />
            <Route path="households" element={<HouseholdsPage />} />
            <Route path="traditions" element={<TraditionsPage />} />
            <Route path="traditions/:entryId" element={<TraditionDetailPage />} />
            <Route path="places" element={<PlacesPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="duplicates" element={<DuplicatesPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="review/:proposalId" element={<ReviewPage />} />
            <Route path="documents" element={<Lazy><DocumentsPage /></Lazy>} />
            <Route path="documents/:documentId" element={<Lazy><DocumentDetailPage /></Lazy>} />
            <Route path="property" element={<Lazy><PropertyListPage /></Lazy>} />
            <Route path="property/:propertyId" element={<Lazy><PropertyDetailPage /></Lazy>} />
            <Route path="import-export" element={<Lazy><ImportExportPage /></Lazy>} />
            <Route path="admin/restore" element={<RestorePeoplePage />} />
            <Route path="admin/members" element={<MembersPage />} />
            <Route path="admin/invitations" element={<InvitationsPage />} />
            <Route path="admin/claims" element={<ClaimsPage />} />
            <Route path="admin/audit" element={<AuditPage />} />
            <Route path="admin/settings" element={<SettingsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
