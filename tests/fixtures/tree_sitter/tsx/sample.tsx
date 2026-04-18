import React, { useState, useEffect } from "react";
import type { FC, ReactNode } from "react";

export interface CardProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export const Card: FC<CardProps> = ({ title, children, className }) => {
  return (
    <div className={`card ${className ?? ""}`}>
      <h2>{title}</h2>
      <div className="card-body">{children}</div>
    </div>
  );
};

export interface ButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary";
}

export const Button: FC<ButtonProps> = ({ label, onClick, disabled = false, variant = "primary" }) => {
  return (
    <button
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
};

export interface UserListProps {
  userId: number;
}

export const UserList: FC<UserListProps> = ({ userId }) => {
  const [items, setItems] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const response = await fetch(`/api/users/${userId}/items`);
      const data = await response.json();
      setItems(data);
      setLoading(false);
    }
    load();
  }, [userId]);

  if (loading) return <span>Loading...</span>;

  return (
    <Card title="User Items">
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Card>
  );
};
