import Link from "next/link";
import styles from "./style.module.css";

export default function HomePage() {
  return (
    <div className={styles.container}>
      <div className={styles.textContainer}>
        <h1 className={styles.title}>
          Travel Smart, Reduce Your Carbon Footprint
        </h1>
        <h2 className={styles.subtitle}>
          Compare the CO₂ emissions of different transportation modes and make
          eco-friendly choices for a greener future
        </h2>
        <Link href="/calculate">
          <button className={styles.button}>Calculate your impact</button>
        </Link>
      </div>
      <div className={styles.illustration}>
        { }
      </div>
    </div>
  );
}
