import { comparison } from "../content";
import { SectionHeader } from "./ui";

export default function Comparison() {
  return (
    <section className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="Why our solution"
          title="Existing approach vs Classora innovation"
          body="Faster capture. Smarter follow-through. Explainable enough for a counsellor to defend."
        />
        <div className="mt-12 overflow-hidden rounded-[24px] border border-[#d7e0ee]">
          <div className="grid grid-cols-[1fr_1.2fr_1.3fr] bg-[#F1F5F9] px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#475569] md:px-6">
            <span>Lens</span>
            <span>Existing approach</span>
            <span>Our innovation</span>
          </div>
          {comparison.map((row, i) => (
            <div
              key={row.axis}
              className={`grid grid-cols-[1fr_1.2fr_1.3fr] gap-2 px-4 py-4 text-[13px] md:px-6 ${i % 2 ? "bg-[#F6F8FC]" : "bg-white"}`}
            >
              <span className="font-semibold text-[#0B1F4A]">{row.axis}</span>
              <span className="text-[#5b6b82]">{row.old}</span>
              <span className="font-medium text-[#0B1F4A]">{row.ours}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
