import "./Header.css";

function Header() {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <span className="brand">
          <span className="brand-mark">◆</span> Agentic Web QA Tester
        </span>
        <a
          className="repo-link"
          href="https://github.com/duashakeel0/Agentic-Web-QA-tester"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
      </div>
    </header>
  );
}

export default Header;
