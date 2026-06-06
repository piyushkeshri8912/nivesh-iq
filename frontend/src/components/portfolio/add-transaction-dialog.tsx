"use client";

import { useEffect, useState, useRef } from "react";
import { addTransaction, updateTransaction, Transaction, TransactionResponse } from "@/lib/api";

interface AddTransactionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  transactionToEdit?: TransactionResponse | null;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// Dynamically generate years list from 2000 up to the current year only (blocks selecting future years)
const currentYearLimit = new Date().getFullYear();
const YEARS = Array.from({ length: currentYearLimit - 2000 + 1 }, (_, idx) => 2000 + idx);

export default function AddTransactionDialog({
  isOpen,
  onClose,
  onSuccess,
  transactionToEdit = null,
}: AddTransactionDialogProps) {
  const [symbol, setSymbol] = useState("");
  const [type, setType] = useState("BUY");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  
  // Custom Calendar State
  const [selectedDate, setSelectedDate] = useState<Date>(() => {
    const now = new Date();
    return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  });
  const [viewMonth, setViewMonth] = useState<number>(() => new Date().getMonth());
  const [viewYear, setViewYear] = useState<number>(() => new Date().getFullYear());
  const [showCalendar, setShowCalendar] = useState(false);
  
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const calendarRef = useRef<HTMLDivElement>(null);

  // Pre-populate fields when editing an existing transaction
  useEffect(() => {
    if (isOpen) {
      if (transactionToEdit) {
        setSymbol(transactionToEdit.symbol);
        setType(transactionToEdit.transaction_type);
        setQuantity(transactionToEdit.quantity.toString());
        setPrice(transactionToEdit.price.toString());
        setFees(transactionToEdit.fees?.toString() || "0");
        
        if (transactionToEdit.executed_at) {
          const d = new Date(transactionToEdit.executed_at);
          setSelectedDate(d);
          setViewMonth(d.getUTCMonth());
          setViewYear(d.getUTCFullYear());
        } else {
          const now = new Date();
          const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
          setSelectedDate(d);
          setViewMonth(now.getMonth());
          setViewYear(now.getFullYear());
        }
      } else {
        // Reset form for new entry
        setSymbol("");
        setType("BUY");
        setQuantity("");
        setPrice("");
        setFees("0");
        
        const now = new Date();
        const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
        setSelectedDate(d);
        setViewMonth(now.getMonth());
        setViewYear(now.getFullYear());
      }
      setShowCalendar(false);
      setError(null);
    }
  }, [transactionToEdit, isOpen]);

  // Click outside listener to dismiss custom calendar popover
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (calendarRef.current && !calendarRef.current.contains(event.target as Node)) {
        setShowCalendar(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  if (!isOpen) return null;

  // Calendar calculations
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstDayIndex = new Date(viewYear, viewMonth, 1).getDay(); // 0 is Sunday, 6 is Saturday

  const blanks = Array(firstDayIndex).fill(null);
  const days = Array.from({ length: daysInMonth }, (_, idx) => idx + 1);
  const gridCells = [...blanks, ...days];

  const now = new Date();
  const currentMonthLimit = now.getMonth();
  const currentYearLimitVal = now.getFullYear();

  const handlePrevMonth = () => {
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    const nextM = viewMonth === 11 ? 0 : viewMonth + 1;
    const nextY = viewMonth === 11 ? viewYear + 1 : viewYear;
    
    // Block navigating to future months
    if (nextY > currentYearLimitVal || (nextY === currentYearLimitVal && nextM > currentMonthLimit)) {
      return;
    }

    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  // Determine if next month chevron should be disabled (in the future)
  const nextM = viewMonth === 11 ? 0 : viewMonth + 1;
  const nextY = viewMonth === 11 ? viewYear + 1 : viewYear;
  const isNextMonthFuture = nextY > currentYearLimitVal || (nextY === currentYearLimitVal && nextM > currentMonthLimit);

  // Validate if day cell is in the future
  const isFutureDate = (day: number) => {
    const cellDate = new Date(Date.UTC(viewYear, viewMonth, day));
    const todayUTC = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    return cellDate > todayUTC;
  };

  const handleDateSelect = (day: number) => {
    const newDate = new Date(Date.UTC(viewYear, viewMonth, day));
    setSelectedDate(newDate);
    setShowCalendar(false);
  };

  const formatInputDate = (date: Date) => {
    const m = date.getUTCMonth() + 1;
    const d = date.getUTCDate();
    const y = date.getUTCFullYear().toString().slice(-2);
    return `${m}/${d}/${y}`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    if (!symbol.trim()) {
      setError("Stock symbol is required.");
      setSubmitting(false);
      return;
    }

    const qty = Number(quantity);
    const prc = Number(price);
    const fee = Number(fees);

    if (isNaN(qty) || qty <= 0) {
      setError("Quantity must be a positive number.");
      setSubmitting(false);
      return;
    }

    if (isNaN(prc) || prc <= 0) {
      setError("Price must be a positive number.");
      setSubmitting(false);
      return;
    }

    // Verify date is not in the future upon final submission
    const todayUTC = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    if (selectedDate > todayUTC) {
      setError("Cannot log transactions with a future date.");
      setSubmitting(false);
      return;
    }

    const payload: Transaction = {
      symbol: symbol.toUpperCase().trim(),
      transaction_type: type,
      quantity: qty,
      price: prc,
      fees: isNaN(fee) ? 0 : fee,
      executed_at: selectedDate.toISOString(),
    };

    try {
      if (transactionToEdit) {
        await updateTransaction(transactionToEdit.id, payload);
      } else {
        await addTransaction(payload);
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to save transaction.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm">
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="w-full max-w-md bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-2xl animate-scale-in text-left">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
              {transactionToEdit ? "Edit Transaction Log" : "Log New Trade"}
            </h3>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-rose-50 border border-rose-100 text-rose-800 text-xs rounded-xl dark:bg-rose-950/20 dark:border-rose-900/40 dark:text-rose-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Stock Symbol
                </label>
                <input
                  type="text"
                  placeholder="e.g. INFY, SBI"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  disabled={!!transactionToEdit}
                  className="w-full px-3.5 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Action
                </label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium"
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Quantity (Shares)
                </label>
                <input
                  type="number"
                  step="any"
                  placeholder="0.0"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className="w-full px-3.5 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Price per Share (₹/$)
                </label>
                <input
                  type="number"
                  step="any"
                  placeholder="0.0"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  className="w-full px-3.5 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Brokerage Fees
                </label>
                <input
                  type="number"
                  step="any"
                  value={fees}
                  onChange={(e) => setFees(e.target.value)}
                  className="w-full px-3.5 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium"
                />
              </div>

              {/* Custom Interactive Calendar Date Picker Input */}
              <div className="space-y-1.5 relative" ref={calendarRef}>
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Purchase Date
                </label>
                <button
                  type="button"
                  onClick={() => setShowCalendar(!showCalendar)}
                  className="w-full px-3.5 py-2 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium flex items-center gap-2 hover:bg-zinc-100/30 dark:hover:bg-zinc-800/10 transition-colors text-left"
                >
                  <svg
                    className="w-5 h-5 text-zinc-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                  </svg>
                  <span>{formatInputDate(selectedDate)}</span>
                </button>

                {/* Calendar Popover Panel Overlay - Opens DOWNWARDS (top-full) with dynamic spacer to prevent clipping */}
                {showCalendar && (
                  <div className="absolute right-0 top-full mt-2 z-50 w-72 bg-white border border-zinc-200 rounded-3xl p-4 shadow-xl dark:bg-zinc-900 dark:border-zinc-800 animate-scale-in">
                    {/* Calendar Header Month & Year Selector chevrons */}
                    <div className="flex justify-between items-center mb-3">
                      <button
                        type="button"
                        onClick={handlePrevMonth}
                        className="p-1 text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
                        </svg>
                      </button>
                      
                      {/* Month and Year Dropdowns */}
                      <div className="flex gap-1.5 items-center">
                        <select
                          value={viewMonth}
                          onChange={(e) => setViewMonth(Number(e.target.value))}
                          className="bg-transparent border-none text-sm font-semibold text-zinc-800 dark:text-zinc-200 py-0.5 px-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 focus:outline-none cursor-pointer"
                        >
                          {MONTHS.map((m, idx) => {
                            const isFutureMonth = viewYear === currentYearLimitVal && idx > currentMonthLimit;
                            return (
                              <option 
                                key={m} 
                                value={idx} 
                                disabled={isFutureMonth}
                                className="bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-250 disabled:opacity-40"
                              >
                                {m.slice(0, 3)}
                              </option>
                            );
                          })}
                        </select>
                        
                        <select
                          value={viewYear}
                          onChange={(e) => {
                            const y = Number(e.target.value);
                            setViewYear(y);
                            if (y === currentYearLimitVal && viewMonth > currentMonthLimit) {
                              setViewMonth(currentMonthLimit);
                            }
                          }}
                          className="bg-transparent border-none text-sm font-semibold text-zinc-800 dark:text-zinc-200 py-0.5 px-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 focus:outline-none cursor-pointer"
                        >
                          {YEARS.map((y) => (
                            <option key={y} value={y} className="bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-250">
                              {y}
                            </option>
                          ))}
                        </select>
                      </div>

                      <button
                        type="button"
                        onClick={handleNextMonth}
                        disabled={isNextMonthFuture}
                        className={`p-1 text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 transition-colors ${
                          isNextMonthFuture ? "opacity-30 cursor-not-allowed" : ""
                        }`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                    </div>

                    {/* Calendar Grid Weekday letters */}
                    <div className="grid grid-cols-7 text-center text-xs font-semibold text-zinc-400 mb-2">
                      <span>S</span>
                      <span>M</span>
                      <span>T</span>
                      <span>W</span>
                      <span>T</span>
                      <span>F</span>
                      <span>S</span>
                    </div>

                    {/* Calendar Days items grid */}
                    <div className="grid grid-cols-7 text-center gap-y-1">
                      {gridCells.map((day, cellIndex) => {
                        if (day === null) {
                          return <div key={`blank-${cellIndex}`} className="w-9 h-9" />;
                        }
                        
                        const isSelected =
                          selectedDate.getUTCDate() === day &&
                          selectedDate.getUTCMonth() === viewMonth &&
                          selectedDate.getUTCFullYear() === viewYear;

                        const isFuture = isFutureDate(day);

                        return (
                          <button
                            key={`day-${day}`}
                            type="button"
                            onClick={() => !isFuture && handleDateSelect(day)}
                            disabled={isFuture}
                            className={`w-9 h-9 text-xs font-semibold flex items-center justify-center mx-auto transition-all ${
                              isSelected
                                ? "bg-indigo-600 text-white rounded-full shadow-md shadow-indigo-600/20"
                                : isFuture
                                ? "text-zinc-300 dark:text-zinc-700 cursor-not-allowed opacity-40"
                                : "text-zinc-800 dark:text-zinc-200 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800"
                            }`}
                          >
                            {day}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {showCalendar && (
              <div className="h-[310px] pointer-events-none" aria-hidden="true" />
            )}

            <div className="flex gap-3 justify-end pt-4 border-t border-zinc-150 dark:border-zinc-800 mt-6">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl border border-zinc-200 dark:border-zinc-800 text-sm font-medium hover:bg-zinc-50 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-medium shadow-md shadow-indigo-600/10 transition-colors disabled:opacity-50"
              >
                {submitting ? "Saving..." : transactionToEdit ? "Update Trade" : "Log Trade"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}