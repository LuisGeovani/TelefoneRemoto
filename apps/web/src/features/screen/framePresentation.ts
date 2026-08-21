export type CandidatePhase = "none" | "decoding" | "awaiting_ack";

export type FramePresentation<T> = Readonly<{
  displayed: T | null;
  candidate: T | null;
  candidatePhase: CandidatePhase;
  displayedConfirmed: boolean;
  confirmedAt: number | null;
}>;

export class FramePresentationMachine<T> {
  private state: FramePresentation<T> = {
    displayed: null,
    candidate: null,
    candidatePhase: "none",
    displayedConfirmed: false,
    confirmedAt: null,
  };

  snapshot(): FramePresentation<T> {
    return this.state;
  }

  begin(candidate: T): boolean {
    if (this.state.candidate !== null) return false;
    this.state = {
      ...this.state,
      candidate,
      candidatePhase: "decoding",
    };
    return true;
  }

  decoded(candidate: T): boolean {
    if (this.state.candidate !== candidate || this.state.candidatePhase !== "decoding") return false;
    this.state = {
      ...this.state,
      candidatePhase: "awaiting_ack",
    };
    return true;
  }

  acknowledged(candidate: T, confirmedAt: number): T | null | undefined {
    if (this.state.candidate !== candidate || this.state.candidatePhase !== "awaiting_ack") return undefined;
    const previous = this.state.displayed;
    this.state = {
      displayed: candidate,
      candidate: null,
      candidatePhase: "none",
      displayedConfirmed: true,
      confirmedAt,
    };
    return previous;
  }

  candidateFailed(candidate: T): boolean {
    if (this.state.candidate !== candidate) return false;
    this.state = {
      ...this.state,
      candidate: null,
      candidatePhase: "none",
    };
    return true;
  }

  invalidate(preserveDisplayed: boolean): FramePresentation<T> {
    const previous = this.state;
    this.state = {
      displayed: preserveDisplayed ? previous.displayed : null,
      candidate: null,
      candidatePhase: "none",
      displayedConfirmed: false,
      confirmedAt: null,
    };
    return previous;
  }
}
