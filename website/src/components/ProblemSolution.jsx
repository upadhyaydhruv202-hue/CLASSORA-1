import { motion } from "framer-motion";
import { challenges } from "../content";
import { SectionHeader, useTilt } from "./ui";
import SolutionArchitecture from "./SolutionArchitecture";

function ChallengeCard({ c, i }) {
  const tilt = useTilt(true, 4);
  return (
    <motion.article
      ref={tilt.ref}
      onMouseMove={tilt.move}
      onMouseLeave={tilt.leave}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ delay: i * 0.06, duration: 0.45 }}
      className="fx-tilt rounded-2xl border border-[#d7e0ee] bg-white p-5 hover:border-[#93C5FD] hover:shadow-[0_16px_32px_rgba(11,31,74,0.07)]"
    >
      <p className="font-display text-2xl text-[#2563EB]">{c.k}</p>
      <h3 className="mt-3 text-[15px] font-semibold text-[#0B1F4A]">{c.title}</h3>
      <p className="mt-2 text-[13px] leading-6 text-[#5b6b82]">{c.body}</p>
    </motion.article>
  );
}

export default function ProblemSolution() {
  return (
    <section id="problem" className="relative py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="The Challenge"
          title="Attendance is still a clipboard problem with student-success consequences."
          body="Institutions collect presence. They rarely convert it into a trusted, explainable support loop."
        />
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" style={{ perspective: "1100px" }}>
          {challenges.map((c, i) => (
            <ChallengeCard key={c.title} c={c} i={i} />
          ))}
        </div>

        <div id="solution" className="mt-20 scroll-mt-24">
          <SectionHeader
            kicker="Our Solution"
            title="Capture → Intelligence → Human Action"
            body="From classroom signals to explainable insights and timely human support."
          />
          <SolutionArchitecture />
        </div>
      </div>
    </section>
  );
}
