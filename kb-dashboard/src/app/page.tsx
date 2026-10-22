"use client";

import FileEditor from "@/components/FileEditor";
import FileTree from "@/components/FileTree";
import PublishBar from "@/components/PublishBar";

export default function KnowledgeBasePage() {
  return (
    <main className="app-shell space-y-5">
      <PublishBar />
      <section className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <FileTree />
        <FileEditor />
      </section>
    </main>
  );
}