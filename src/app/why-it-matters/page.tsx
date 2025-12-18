"use client";

import styles from "./why-it-matters.module.css";
import Link from "next/link";
import Image from "next/image";

export default function WhyItMattersPage() {
  const stats = [
    { value: "24%", label: "of global CO₂ emissions come from transportation" },
    { value: "72%", label: "of transport emissions come from road vehicles" },
    { value: "7%",  label: "annual growth rate of aviation emissions" },
    { value: "0.05 kg", label: "CO₂ per passenger-km by train (vs 0.17 kg by car)" },
  ];

  const articles = [
    {
      title: "Mobilité et climat : vous avez dit urgence ?",
      source: "Cerema",
      url: "https://www.cerema.fr/fr/actualites/mobilite-climat-vous-avez-dit-urgence",
      imageUrl: "/images/why-it-matters/cerema-forest-co2.png",
      preview: "Analyse des solutions de mobilité durable et focus sur l’impact individuel sur le climat.",
    },
    {
      title: "Qualité de l’air : Sources de pollution et effets sur la santé",
      source: "Ministère de la Santé",
      url: "https://sante.gouv.fr/sante-et-environnement/air-exterieur/qualite-de-l-air-exterieur-10984/article/qualite-de-l’air-sources-de-pollution-et-effets-sur-la-sante",
      imageUrl: "/images/why-it-matters/air_france.png",
      preview: "Facteurs de pollution atmosphérique liés au transport et impacts sur la santé publique en zones urbaines.",
    },
    {
      title: "Ambient (outdoor) air pollution",
      source: "World Health Organization",
      url: "https://www.who.int/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health",
      imageUrl: "/images/why-it-matters/air_quality.png",
      preview: "Explore the link between outdoor air pollution from transport and respiratory-cardiovascular health issues worldwide.",
    },
    {
      title: "The Future of Rail – Analysis",
      source: "International Energy Agency",
      url: "https://www.iea.org/reports/the-future-of-rail",
      imageUrl: "/images/why-it-matters/rail.png",
      preview: "Discover how shifting freight and passenger traffic to rail can cut CO₂ emissions dramatically by 2050.",
    },
  ];

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
        <h1 className={styles.title}>Why It Matters</h1>

        <section className={styles.section}>
          <h2>Climate Change and Transportation</h2>
          <p>
            Every trip you take leaves a carbon footprint. From daily commutes in
            the city to long-haul flights, our collective journeys accelerate
            global warming, fuel extreme weather events, and threaten
            vulnerable ecosystems — from melting ice caps to rising coastlines.
          </p>
          <div className={styles.statsGrid}>
            {stats.map((stat, idx) => (
              <div key={idx} className={styles.statCard}>
                <div className={styles.statValue}>{stat.value}</div>
                <div className={styles.statLabel}>{stat.label}</div>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <h2>Our Mission</h2>
          <p>
            We aim to help you understand the impact of your travel choices.
            Compare CO₂ emissions of different transport modes to make more
            eco-friendly decisions.
          </p>
          <p>
            By choosing the train over the car, cycling instead of flying short
            distances, or carpooling rather than driving alone, you can
            significantly reduce your carbon footprint.
          </p>
        </section>

        <section className={styles.section}>
          <h2>They Talk About It</h2>
          <div className={styles.articlesGrid}>
            {articles.map((article, idx) => (
              <div key={idx} className={styles.articleCard}>
                <Image
                  src={article.imageUrl}
                  alt={article.title}
                  className={styles.articleImage}
                  width={300}
                  height={200}
                />
                <h3 className={styles.articleTitle}>{article.title}</h3>
                <p className={styles.articleSource}>{article.source}</p>
                <p className={styles.articlePreview}>{article.preview}</p>
                <div className={styles.articleAction}>
                  <Link
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.articleButton}
                  >
                    Read more
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
