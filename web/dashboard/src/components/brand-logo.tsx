import Image from "next/image";
import logo from "@/assets/logo.png";

/** The MedMusketeer logo on a white tile, so it reads on the dark sidebar as well as on light cards. */
export function BrandLogo({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <Image
      src={logo}
      alt=""
      aria-hidden
      width={size}
      height={size}
      unoptimized
      className={`shrink-0 rounded-[var(--radius-sm)] bg-white ${className}`}
    />
  );
}
