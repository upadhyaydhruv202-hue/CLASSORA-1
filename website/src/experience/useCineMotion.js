import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

export default function useCineMotion() {
  const prefersReduce = useReducedMotion();
  const [toggled, setToggled] = useState(false);

  useEffect(() => {
    const apply = (value) => setToggled(Boolean(value));
    apply(document.documentElement.classList.contains("reduce-motion"));
    const onReduce = (event) => apply(event.detail);
    window.addEventListener("cine-reduce", onReduce);
    return () => window.removeEventListener("cine-reduce", onReduce);
  }, []);

  return Boolean(prefersReduce || toggled);
}
