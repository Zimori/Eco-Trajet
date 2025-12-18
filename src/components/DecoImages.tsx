import Image from "next/image";

const decoImages = [
  { src: "/images/deco1.png", className: "deco1" },
  { src: "/images/deco2.png", className: "deco2" },
  { src: "/images/deco3.png", className: "deco3" },
  { src: "/images/deco4.png", className: "deco4" },
];

export default function DecoImages({ classNamePrefix }: { classNamePrefix: string }) {
  return (
    <>
      {decoImages.map((img) => (
        <Image
          key={img.className}
          src={img.src}
          alt=""
          aria-hidden="true"
          className={classNamePrefix + " " + img.className}
          width={120}
          height={120}
        />
      ))}
    </>
  );
}
