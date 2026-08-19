import { motion } from "framer-motion";
import { team } from "../content";
import { SectionHeader, useTilt } from "./ui";

function LinkedInIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M4.98 3.5C4.98 4.88 3.88 6 2.5 6S0 4.88 0 3.5 1.12 1 2.5 1s2.48 1.12 2.48 2.5zM.24 8.98h4.52V24H.24zM8.23 8.98h4.33v2.05h.06c.6-1.14 2.08-2.34 4.28-2.34 4.58 0 5.42 3.01 5.42 6.93V24h-4.51v-7.43c0-1.77-.03-4.05-2.47-4.05-2.47 0-2.85 1.93-2.85 3.92V24H8.23z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58 0-.28-.01-1.02-.02-2-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.33-1.76-1.33-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.34-5.47-5.95 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.62-2.81 5.65-5.49 5.95.43.37.81 1.1.81 2.22 0 1.61-.01 2.91-.01 3.31 0 .32.22.7.82.58A12.01 12.01 0 0 0 24 12.5C24 5.87 18.63.5 12 .5z" />
    </svg>
  );
}

const socialClass =
  "relative z-10 inline-flex cursor-pointer items-center justify-center rounded-full border border-[#d7e0ee] p-2 text-[#0B1F4A] no-underline transition duration-200 hover:-translate-y-0.5 hover:scale-110 hover:border-[#2563EB] hover:bg-[#F6F8FC] hover:text-[#2563EB] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2563EB] group-hover:border-[#93C5FD]";

function SocialLink({ href, label, children }) {
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} className={socialClass}>
      {children}
    </a>
  );
}

function TeamCard({ m, i }) {
  const tilt = useTilt(true, 4);
  return (
    <motion.article
      ref={tilt.ref}
      onMouseMove={tilt.move}
      onMouseLeave={tilt.leave}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: i * 0.04 }}
      className="fx-tilt group flex h-full min-w-0 flex-col rounded-2xl border border-[#d7e0ee] bg-white p-6 hover:border-[#93C5FD] hover:shadow-[0_20px_40px_rgba(11,31,74,0.08)]"
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#0B1F4A] text-sm font-bold tracking-wide text-white transition duration-300 group-hover:shadow-[0_0_0_4px_rgba(37,99,235,0.16)]">
        {m.initials}
      </div>
      <h3 className="mt-4 break-words text-[16px] font-semibold leading-snug text-[#0B1F4A]">{m.name}</h3>
      <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#2563EB]">{m.role}</p>
      <p className="mt-2 flex-1 text-[13px] leading-6 text-[#5b6b82]">{m.expertise}</p>
      {(m.github || m.linkedin) && (
        <div className="relative z-10 mt-4 flex gap-2">
          <SocialLink href={m.github} label={`${m.name} on GitHub`}>
            <GitHubIcon />
          </SocialLink>
          <SocialLink href={m.linkedin} label={`${m.name} on LinkedIn`}>
            <LinkedInIcon />
          </SocialLink>
        </div>
      )}
    </motion.article>
  );
}

export default function Team() {
  return (
    <section id="team" className="py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="Team"
          title="Built for SIH 2026 — classroom-first, institution-credible."
          body="A six-person team spanning product, design, frontend, and research."
        />
        <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" style={{ perspective: "1100px" }}>
          {team.map((m, i) => (
            <TeamCard key={m.name} m={m} i={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
