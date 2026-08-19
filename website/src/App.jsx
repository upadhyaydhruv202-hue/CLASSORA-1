import { useCallback, useEffect, useState } from "react";
import { AnimatePresence } from "framer-motion";
import Loading from "./experience/Loading";
import Experience from "./experience/Experience";
import ClassroomApp from "./classroom/App";

function currentPath() {
  return window.location.pathname || "/";
}

export default function App() {
  const [path, setPath] = useState(currentPath);
  const [boot, setBoot] = useState(() => {
    if (currentPath().startsWith("/app")) return false;
    try {
      return sessionStorage.getItem("classora_booted") !== "1";
    } catch {
      return true;
    }
  });
  const done = useCallback(() => {
    try {
      sessionStorage.setItem("classora_booted", "1");
    } catch {
      /* ignore */
    }
    setBoot(false);
  }, []);

  useEffect(() => {
    const sync = () => setPath(currentPath());
    const onClick = (event) => {
      const link = event.target.closest?.("a[href]");
      if (!link || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.target && link.target !== "_self") return;
      let url;
      try {
        url = new URL(link.href, window.location.origin);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      const nextPath = url.pathname || "/";
      const isApp = nextPath.startsWith("/app");
      const isHome = nextPath === "/";
      if (!isApp && !isHome) return;
      if (nextPath === window.location.pathname && url.search === window.location.search) return;
      event.preventDefault();
      window.history.pushState({}, "", `${nextPath}${url.search}`);
      setPath(nextPath);
      window.scrollTo(0, 0);
    };
    window.addEventListener("popstate", sync);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("popstate", sync);
      document.removeEventListener("click", onClick);
    };
  }, []);

  if (path.startsWith("/app")) {
    return <ClassroomApp />;
  }

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[90] focus:rounded-full focus:bg-white focus:px-4 focus:py-2 focus:text-[#0F172A]"
      >
        Skip to content
      </a>
      <AnimatePresence>{boot && <Loading key="boot" onDone={done} />}</AnimatePresence>
      <Experience active={!boot} />
    </>
  );
}
