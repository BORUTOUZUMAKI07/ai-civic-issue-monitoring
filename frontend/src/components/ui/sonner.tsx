import { Toaster as Sonner } from "sonner";

function Toaster(props: React.ComponentProps<typeof Sonner>) {
  return <Sonner {...props} />;
}

export { Toaster };
