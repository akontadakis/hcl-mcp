# Third-Party Notices

`hcl-mcp` is licensed under the **MIT License** (see [`LICENSE`](LICENSE)).

It does **not bundle** any third-party binaries. However, it is an **independent implementation
that derives certain spectral algorithms from Lark Spectral Lighting** (a prior implementation of
the same science), it **invokes** the Radiance and Daysim engines as external subprocesses, and it
**depends on** several Python libraries installed via `pip`/`uv`. Those components are covered by
their own licenses, reproduced and attributed below.

The most important obligation: hcl-mcp's spectral algorithms are derived from **Lark Spectral
Lighting**, which is distributed under a **Modified 3-Clause BSD License**. That license requires the
copyright notice and conditions to be retained, and forbids using the "Lark" name to endorse or name
derived products — this project is therefore named `hcl-mcp`, not "Lark", and the Lark notice is
reproduced in full below.

---

## 1. Lark Spectral Lighting — Modified 3-Clause BSD License

**Source:** Lark Spectral Lighting v1.0 / v2.0 / v3.0 — Mehlika Inanici (University of Washington),
ZGF Architects LLP, Clotilde Pierson (EPFL / Oregon State University), Myrta Gkaintatzi-Masouti
(Eindhoven University of Technology), Bo Jung & Zining Cheng (University of Washington).
https://faculty.washington.edu/inanici/Lark/Lark_home_page.html

> Lark Spectral Lighting Software License, Version 3.0 — Modified 3-Clause BSD License
> (https://opensource.org/licenses/BSD-3-Clause)
>
> Copyright 2015–2022 University of Washington (Mehlika Inanici, Ph.D.) and ZGF Architects LLP
> &lt;Lark Spectral Lighting v1.0&gt;; and
> Copyright 2022 EPFL, Oregon State University (Clotilde Pierson, Ph.D.) and Eindhoven University of
> Technology (Myrta Gkaintatzi-Masouti, M.Sc.) &lt;Lark Spectral Lighting v2.0&gt;; and
> Copyright 2023 University of Washington (Bo Jung, M.Sc., Mehlika Inanici, Ph.D., Zining Cheng,
> M.Sc.) and ZGF Architects LLP &lt;Lark Spectral Lighting v3.0&gt;
>
> Redistribution and use in source and binary forms, with or without modification, are permitted
> provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions
>    and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of
>    conditions and the following disclaimer in the documentation and/or other materials provided
>    with the distribution.
> 3. Neither the name of the copyright holder nor the names of its contributors may be used to
>    endorse or promote products derived from this software without specific prior written
>    permission.
>    - (a) The name "Lark Spectral Lighting" and/or "Lark" and its logo must not be used to endorse
>      or promote products derived from this software without prior written permission.
>    - (b) Products derived from this software may not be called "Lark Spectral Lighting" and/or
>      "Lark", nor may "Lark Spectral Lighting" and/or "Lark" appear in their name, without prior
>      written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
> IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
> FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
> CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
> DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
> DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
> IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
> OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The name "Lark Spectral Lighting" and its logo are the property of the University of Washington
(Mehlika Inanici, Ph.D.) and ZGF Architects LLP and cannot be used without permission.

---

## 2. Radiance — The Radiance Software License, Version 1.0

**Source:** Radiance synthetic imaging system — Lawrence Berkeley National Laboratory.
https://www.radiance-online.org/  ·  https://radsite.lbl.gov/

hcl-mcp invokes Radiance binaries (`oconv`, `rtrace`, `rpict`, `gendaylit`, `gendaymtx`, `rfluxmtx`,
`rcontrib`, `dctimestep`, `ies2rad`, `evalglare`, …) as external subprocesses; it does not include or
distribute Radiance. As required by the Radiance license:

> This product includes Radiance software (https://radsite.lbl.gov/) developed by the Lawrence
> Berkeley National Laboratory (https://www.lbl.gov/).

> The Radiance Software License, Version 1.0
>
> Copyright (c) 1990–2002 The Regents of the University of California, through Lawrence Berkeley
> National Laboratory. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, are permitted
> provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions
>    and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of
>    conditions and the following disclaimer in the documentation and/or other materials provided
>    with the distribution.
> 3. The end-user documentation included with the redistribution, if any, must include the following
>    acknowledgment: "This product includes Radiance software (https://radsite.lbl.gov/) developed by
>    the Lawrence Berkeley National Laboratory (https://www.lbl.gov/)." Alternately, this
>    acknowledgment may appear in the software itself, if and wherever such third-party
>    acknowledgments normally appear.
> 4. The names "Radiance," "Lawrence Berkeley National Laboratory" and "The Regents of the University
>    of California" must not be used to endorse or promote products derived from this software
>    without prior written permission. For written permission, please contact radiance@radsite.lbl.gov.
> 5. Products derived from this software may not be called "Radiance", nor may "Radiance" appear in
>    their name, without prior written permission of Lawrence Berkeley National Laboratory.
>
> THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESSED OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
> LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL Lawrence Berkeley National Laboratory OR ITS CONTRIBUTORS BE LIABLE
> FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES … ARISING IN ANY
> WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

---

## 3. Daysim

**Source:** Daysim (`ds_shortterm`, `epw2wea`) — originally National Research Council Canada (NRC) and
Fraunhofer Institute for Solar Energy Systems (ISE); community fork maintained at
https://github.com/MITSustainableDesignLab/Daysim

hcl-mcp does **not** bundle Daysim. The `build_daysim` tool clones the repository above and builds the
binaries **from source** on the user's machine. Daysim is source-available (research/academic) and is
**not** under an OSI-approved open-source license. Consult the Daysim repository for its authoritative
license terms before redistributing the source or any binaries you build from it.

---

## 4. Python dependencies

Installed via `pip`/`uv` (not vendored into this repository). Licenses verified from the installed
package metadata:

| Package | License (SPDX) | Project |
|---|---|---|
| `fastmcp` | Apache-2.0 | https://github.com/jlowin/fastmcp |
| `mcp` (Model Context Protocol SDK) | MIT | https://github.com/modelcontextprotocol/python-sdk |
| `pydantic` / `pydantic-core` | MIT | https://github.com/pydantic/pydantic |
| `colour-science` (`colour`) | BSD-3-Clause | https://www.colour-science.org/ |
| `annotated-types` | MIT | https://github.com/annotated-types/annotated-types |
| `typing-extensions` | PSF-2.0 | https://github.com/python/typing_extensions |

Full license texts:
- **MIT** — https://opensource.org/license/mit
- **BSD-3-Clause** — https://opensource.org/license/bsd-3-clause
- **Apache-2.0** — https://www.apache.org/licenses/LICENSE-2.0
- **PSF-2.0** — https://docs.python.org/3/license.html

---

## 5. Scientific methods & data

The algorithms implemented here follow published methods (CIE S 026:2018; Inanici, Brennan & Clark
2015; Jung, Cheng, Brennan & Inanici 2023; Amundadottir 2016; Subramaniam 2017; Khademagha 2021;
EnergyPlus Engineering Reference; IESNA LM-63). These are scientific references, not licensed
software; see the **References & Citations** table in [`README.md`](README.md) for the full list.
Embedded reference spectra are CIE/standards-derived or representative approximations as documented in
the source and the technical review.
