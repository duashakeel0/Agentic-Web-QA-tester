function PlaceholderPage({ title, note }: { title: string; note: string }) {
  return (
    <div>
      <h1 style={{ fontSize: 28, margin: "0 0 0.5rem" }}>{title}</h1>
      <p style={{ color: "var(--text)", fontSize: 14.5 }}>{note}</p>
    </div>
  );
}

export default PlaceholderPage;
