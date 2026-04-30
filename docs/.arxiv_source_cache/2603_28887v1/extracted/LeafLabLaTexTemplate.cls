\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{LeafLabLaTexTemplate}
\LoadClassWithOptions{article}

% Layout %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage[top=2.25cm, bottom=2.5cm, left=2.5cm, right=2.5cm, columnsep=0.65cm]{geometry}
\RequirePackage{microtype}
\RequirePackage{placeins}
\RequirePackage{hyphenat}
\RequirePackage{setspace}
\RequirePackage{parskip}
\RequirePackage[latin, english]{babel}
\RequirePackage{lipsum}
\RequirePackage{etoolbox}

\RequirePackage{XCharter}
\RequirePackage[scaled=1.1]{zlmtt}

\DisableLigatures[f]{family=sf*} 

% Graphics %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage{graphicx}
\RequirePackage{subcaption}

% Tables %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage{booktabs}
\RequirePackage{nicematrix}
\RequirePackage{multirow}
\RequirePackage{bm}
\newcommand{\nm}[1]{#1}

% Colorful stuff %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage[most]{tcolorbox}
\RequirePackage{xcolor}
\definecolor{wblue}{RGB}{52,204,204}
\definecolor{wyellow}{RGB}{255,192,0}
\definecolor{wfg}{HTML}{1C2B33}
\definecolor{citypink}{RGB}{227, 108, 194}
\definecolor{leafblue}{RGB}{37, 53, 90}
\definecolor{linkred}{RGB}{225, 97, 98}
\definecolor{absbg}{RGB}{246, 249, 250}

% References %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage{hyperref}
\RequirePackage[noabbrev,nameinlink]{cleveref}
\hypersetup{
  colorlinks,
  linkcolor=leafblue,
  citecolor=linkred,
  urlcolor=leafblue,
}

% \RequirePackage[round,authoryear]{natbib}
\RequirePackage[square,numbers,sort&compress]{natbib}
\def\bibfont{\small}

% Section and caption format %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage{titlesec}
\titleformat*{\paragraph}{\itshape}
\titleformat*{\section}{\Large\bfseries}
\titleformat*{\subsection}{\large\bfseries}
\titleformat*{\subsubsection}{\normalsize\bfseries}
\DeclareTextFontCommand{\textbf}{\bfseries}

\RequirePackage{caption}
\DeclareCaptionLabelSeparator{custom}{}
\DeclareCaptionFormat{custom}{{\textbf{#1 #2}} #3}
\captionsetup{singlelinecheck=false,format=custom,labelsep=custom,font=small}
\captionsetup[sub]{singlelinecheck=true,format=custom,labelsep=custom,font=small}


\renewcommand*\ttdefault{cmvtt}
\RequirePackage[T1]{fontenc}

% Authors, affiliations, infos %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\renewcommand\addtolist[5][]{
  \begingroup
    \if\relax#3\relax\def\sep{}\else\def\sep{#5}\fi
    \let\protect\@unexpandable@protect 
    \xdef#3{\expandafter{#3}\sep #4[#1]{#2}}%
  \endgroup
}

\newcommand\authorlist{}
\newcommand\authorformat[2][]{{\bfseries #2$^{#1}$}}
\renewcommand\author[2][]{\addtolist[#1]{#2}{\authorlist}{\authorformat}{, }}

\newcommand\affiliationlist{}
\newcommand\affiliationformat[2][]{{\normalsize $^{#1}$#2}}
\newcommand\affiliation[2][]{\addtolist[#1]{#2}{\affiliationlist}{\affiliationformat}{, }}

\newcommand\contributionlist{}
\newcommand\contributionformat[2][]{{\small $^{#1}$#2}}
\newcommand\contribution[2][]{\addtolist[#1]{#2}{\contributionlist}{\contributionformat}{, }}

\newcommand\metadatalist{}
\newcommand\metadataformat[2][]{{\small {\bfseries #1:} #2}}
\newcommand\metadata[2][]{\addtolist[#1]{#2}{\metadatalist}{\metadataformat}{\par}}

\renewcommand{\abstract}[1]{\def\abstractlist{{\color{wfg} #1}}}
\newcommand{\email}[1]{\href{mailto:#1}{\texttt{#1}}}

\renewcommand\date[1]{\metadata[Date]{#1}}
\newcommand\correspondence[1]{\metadata[Correspondence]{#1}}

\renewcommand{\title}[1]{\newcommand{\titlelist}{\bfseries #1}}

\newcommand{\beginappendix}{\appendix{\huge Appendix\par}}

% Titlebox %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\newcommand{\mymaketitle}{%
  
  {
    \raggedright
    \nohyphens
    
    \raggedright 
    \setlength{\parindent}{0pt}
    {\fontsize{23pt}{28pt}\selectfont
     \raisebox{-0.2\height}{\includegraphics[height=1.1cm]{figures/icons/occsim_logo.png}}\hspace{0.15cm}%
     \titlelist\par}
    % ---------------------------------------------
    \vskip 0.25cm
    
    {\authorlist\par}
    \vskip 0.15cm
    
    {\affiliationlist\par}
    
    {\contributionlist\par}
  }
  
  \vskip 0.6cm

  \tcbset{enhanced,frame hidden, colback=absbg}
  \tcbset{left=0.5cm, right=0.5cm, top=0.5cm, bottom=0.5cm, arc=16pt}
  \tcbset{before skip=0pt, grow to left by=1.5pt, grow to right by=1.5pt}
  
  \begin{tcolorbox}
    \setlength{\parindent}{0cm}
    \setlength{\parskip}{0cm}
    
    \abstractlist\par
    
    \vskip 0.5cm 
    {
      \raggedright
      \setlength{\parskip}{0cm}
      \ifdefempty{\metadatalist}{}{%
        \begin{minipage}[c]{0.65\textwidth}
            \vspace{0pt}
            \metadatalist
        \end{minipage}%
        \hfill
        \begin{minipage}[c]{0.3\textwidth}
            \flushright 
            \href{https://leaf.utias.utoronto.ca/}{\includegraphics[width=3cm]{figures/icons/leaf_template_logo.png}}
        \end{minipage}\par
      }
    }
  \end{tcolorbox}
  \tcbset{reset}

  \FloatBarrier
}

\if@twocolumn%
\renewcommand{\maketitle}{
\twocolumn[%
  \mymaketitle
  \vskip 0.38cm
]
}%
\else%
\renewcommand{\maketitle}{
  \mymaketitle
}%
\fi

\newcommand\blfootnote[1]{%
  \begingroup
  \renewcommand\thefootnote{}\footnote{#1}%
  \addtocounter{footnote}{-1}%
  \endgroup
}