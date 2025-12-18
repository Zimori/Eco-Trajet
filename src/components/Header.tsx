"use client";

import { useState } from "react";
import styles from "./style.module.css";
import Image from "next/image";
import Link from "next/link";

export default function Header() {
  const [noStyle, setNoStyle] = useState(false);

  const toggleStyle = () => {
    if (noStyle) {
      document.body.classList.remove("no-style");
    } else {
      document.body.classList.add("no-style");
    }
    setNoStyle(!noStyle);
  };

  return (
    <header className={`${styles.header} ${noStyle ? styles.noStyle : ""}`}>
      <nav className={styles.nav}>
        <div className={styles.logo}>
          <Link href="/">
            <Image
              src="/images/logoHome.png"
              alt="Logo de l'app"
              width={30} // Largeur de l'image
              height={20} // Hauteur de l'image
              style={{ width: "auto", height: "auto" }}
            />
          </Link>
        </div>
        <ul className={styles.navLinks}>
          <li><Link href="/calculate">Try our calculations</Link></li>
          <li><Link href="/why-it-matters">Why It Matters</Link></li>
          <li><Link href="/about-us">About Us</Link></li>
        </ul>
        <div className={styles.actions}>
          <button className={styles.signIn}>Sign In</button>
          <label className={styles.switch}>
            <input type="checkbox" onChange={toggleStyle} />
            <span className={styles.slider}></span>
          </label>
        </div>
      </nav>
    </header>
  );
}