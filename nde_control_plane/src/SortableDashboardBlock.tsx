import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ReactNode } from "react";

type Props = {
  id: string;
  children: ReactNode;
};

export function SortableDashboardBlock({ id, children }: Props) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 3 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`dashboard-sortable-block${isDragging ? " is-dragging" : ""}`}
    >
      <button
        type="button"
        className="dashboard-drag-handle"
        {...attributes}
        {...listeners}
        aria-label="Drag to reorder section"
        title="Drag to reorder"
      >
        ⠿
      </button>
      <div className="dashboard-sortable-body">{children}</div>
    </div>
  );
}
