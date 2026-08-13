import type { ReactNode } from "react";
import Header from "../shared-components/Header";
import Footer from "../shared-components/Footer";
import "./MainLayout.css";

function MainLayout({ children }: { children: ReactNode }) {
  return (
    <div className="layout">
      <Header />
      <main className="layout-main">{children}</main>
      <Footer />
    </div>
  );
}

export default MainLayout;
