'use client'

import styles from "./about-us.module.css";
import Image from "next/image";

export default function AboutUsPage() {
  return (
    <div className={styles.pageWrapper}>
      <Image
        src="/images/deco1.png"
        alt=""
        aria-hidden="true"
        className={styles.deco1}
        width={120}
        height={120}
      />
      <Image
        src="/images/deco2.png"
        alt=""
        aria-hidden="true"
        className={styles.deco2}
        width={120}
        height={120}
      />
      <Image
        src="/images/deco3.png"
        alt=""
        aria-hidden="true"
        className={styles.deco3}
        width={120}
        height={120}
      />
      <Image
        src="/images/deco4.png"
        alt=""
        aria-hidden="true"
        className={styles.deco4}
        width={120}
        height={120}
      />
    <div className={styles.container}>
      <h1 className={styles.title}>About Us</h1>

      <section className={styles.section}>
        <h2>Project</h2>
        <p>
          Créer une application web interactive permettant de comparer les émissions de CO₂ selon différents modes de transport destinée au grand public en crowdsourcing (en mode interactif).
          L’application devra :

          Permettre aux utilisateurs d’entrer un itinéraire et d’obtenir une estimation des émissions de CO₂ selon plusieurs modes de transport.
          Fournir une visualisation graphique des résultats (graphiques, cartes interactives…).
          S’appuyer sur des données réelles (facteurs d’émission officiels, API externes...).
        </p>
      </section>

      <section className={styles.section}>
        <h2>Our Team</h2>

        <div className={styles.teamGrid}>
          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> Frontend and Backend Developer</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
              </div>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> VM Specialist</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
              </div>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> UI/UX Designer</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
              </div>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> VM and Frontend Developer</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
              </div>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> Backend Developer</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
              </div>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.teamMemberSection}>
            <h2>[REDACTED]</h2>
            <div className={styles.memberInfo}>
              <div className={styles.memberPhoto}>
                <div className={styles.photoPlaceholder}></div>
              </div>
              <div className={styles.memberDetails}>
                <p><strong>Numéro étudiant:</strong> [REDACTED]</p>
                <p><strong>Rôle:</strong> Database Specialist</p>
                <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p> 
              </div>
            </div>
          </section>
        </div>
      </section>

      <section className={styles.section}>
        <h2>Our Professors</h2>

        <div className={styles.professorsGrid}>
          {/* [REDACTED] */}
          <section className={styles.professorMember}>
            <h3>[REDACTED]</h3>
            <div className={styles.professorPhoto}>
              <div className={styles.professorPlaceholder}></div>
            </div>
            <div className={styles.professorDetails}>
              <p><strong>Rôle:</strong> Responsable de l&apos;UE, Orga, Support</p>
              <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.professorMember}>
            <h3>[REDACTED]</h3>
            <div className={styles.professorPhoto}>
              <div className={styles.professorPlaceholder}></div>
            </div>
            <div className={styles.professorDetails}>
              <p><strong>Rôle:</strong> Support BD</p>
              <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
            </div>
          </section>

          {/* [REDACTED] */}
          <section className={styles.professorMember}>
            <h3>[REDACTED]</h3>
            <div className={styles.professorPhoto}>
              <div className={styles.professorPlaceholder}></div>
            </div>
            <div className={styles.professorDetails}>
              <p><strong>Rôle:</strong> Support Prog Web</p>
              <p><strong>Contact:</strong> <a href="mailto:[REDACTED]">[REDACTED]</a></p>
            </div>
          </section>
        </div>
      </section>
    </div>
    </div>
  );
}
